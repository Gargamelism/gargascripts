import argparse
import subprocess
import os
import glob
import sys
import importlib
import boto3
import botocore
import json
import time
from pprint import pprint
from configparser import ConfigParser
from pathlib import Path


def get_option(what_to_choose, options, sort_key=None):
    if not options:
        print(f"No {what_to_choose} found")
        return

    if not sort_key:
        sort_key = lambda name: name

    if len(options) == 1:
        print(f"Only one {what_to_choose} found {sort_key(options[0])}")
        return options[0]

    options = sorted(options, key=sort_key)
    options_prompt = [
        f"{idx}) {sort_key(name)}" for idx, name in enumerate(options) if name
    ]

    print(f"Please choose {what_to_choose}:\n")
    print("\n".join(options_prompt))
    idx = int(input())

    return options[idx]


def update_list_value_based_on_key(list, key, value):
    for line in list:
        if key in line:
            list[list.index(line)] = f"{key}={value}"
            return list
    else:
        list.append(f"{key}={value}")
        return list


def get_profile():
    process = subprocess.Popen(
        "aws configure list-profiles", shell=True, stdout=subprocess.PIPE
    )
    process.wait()
    profiles = process.stdout.read().decode().split("\n")
    clean_profiles = [profile.strip() for profile in profiles]

    return get_option("profile", clean_profiles)


def setup_basic_env(parsed_args):
    return parsed_args


def get_aws_profile_conf(profile):
    # get profile settings
    aws_config = ConfigParser()
    aws_config.read(os.path.join(os.path.expanduser("~"), ".aws/config"))

    section_name = next(
        profile_name
        for profile_name in aws_config.sections()
        if profile in profile_name
    )

    return aws_config[section_name]


def get_profile_credentials(boto_client, profile):
    role_credentials_response = {}
    retries = 5
    while retries > 0:
        try:
            profile_section = get_aws_profile_conf(profile)

            # get access token
            sso_cache_files = glob.glob(
                os.path.join(os.path.expanduser("~"), ".aws/sso/cache/*")
            )
            latest_cache_path = max(sso_cache_files, key=os.path.getctime)
            latest_cache_conf = None
            with open(latest_cache_path, "r") as latest_cache_file:
                latest_cache_conf = json.loads(latest_cache_file.read())

            sso_region = profile_section.get("sso_region", "us-west-2")
            sso_client = boto_client.client("sso", sso_region)

            role_credentials_response = sso_client.get_role_credentials(
                roleName=profile_section["sso_role_name"],
                accountId=profile_section["sso_account_id"],
                accessToken=latest_cache_conf.get("accessToken"),
            )
        except botocore.exceptions.ClientError as err:
            print(err)
            print(f"retrying more <{retries}> times")
            time.sleep(1)
        finally:
            retries -= 1

    return role_credentials_response.get("roleCredentials")


def save_profile_credentials(profile_credentials):
    # pprint(profile_credentials)
    credentials_path = os.path.join(os.path.expanduser("~"), ".aws/credentials")

    aws_credentials = ConfigParser()
    aws_credentials.read(credentials_path)

    if not aws_credentials.has_section("default"):
        aws_credentials.add_section("default")

    aws_credentials["default"]["aws_access_key_id"] = profile_credentials.get(
        "accessKeyId"
    )
    aws_credentials["default"]["aws_secret_access_key"] = profile_credentials.get(
        "secretAccessKey"
    )
    aws_credentials["default"]["aws_session_token"] = profile_credentials.get(
        "sessionToken"
    )

    aws_credentials.write(open(credentials_path, "w"))


def login(parsed_args):
    print("logging in")

    process = subprocess.Popen(
        f"aws sso login --profile {parsed_args.profile}", shell=True
    )
    process.wait()

    # write credentials so local processes can authenticate
    profile_credentials = get_profile_credentials(
        parsed_args.boto_client, parsed_args.profile
    )
    save_profile_credentials(profile_credentials)


def is_logged_in(parsed_args):
    sts_client = boto_client.client("sts")

    # check if there's an active connection
    try:
        caller_identity = sts_client.get_caller_identity()
        parsed_args.caller_identity = caller_identity
        print(caller_identity)
    except botocore.exceptions.UnauthorizedSSOTokenError as error:
        print(error)
        return False
    except botocore.exceptions.SSOTokenLoadError as error:
        print(error)
        return False

    profile_conf = get_aws_profile_conf(parsed_args.profile)

    return caller_identity.get("Account") == profile_conf.get("sso_account_id")


def connect_to_internal_package_managers(parsed_args):
    print("login to codeartifact")

    ACCOUNT_NUMBER = ""
    pip_process = subprocess.Popen(
        f"aws codeartifact login --tool pip --repository pypi-store --domain swc-eu-west-1 --domain-owner {ACCOUNT_NUMBER} --region eu-west-1 --profile master",
        shell=True,
    )

    npm_process = subprocess.Popen(
        "aws codeartifact login --tool npm --repository main --domain swc-eu-west-1 --domain-owner {ACCOUNT_NUMBER} --region eu-west-1",
        shell=True,
    )

    pip_process.wait()
    npm_process.wait()


def connect_to_eks(parsed_args):
    print("connecting to eks")

    eks_client = parsed_args.boto_client.client("eks")

    clusters = eks_client.list_clusters().get("clusters")
    if not clusters:
        print("No EKS clusters found")
        return

    cluster_name = clusters[0]
    if len(clusters) > 1:
        cluster_name = get_option("cluster", clusters)

    print(
        f"aws eks --region {os.environ['AWS_REGION']} update-kubeconfig --name {cluster_name}"
    )
    eks_login_process = subprocess.Popen(
        f"aws eks --region {os.environ['AWS_REGION']} update-kubeconfig --name {cluster_name}",
        shell=True,
    )
    eks_login_process.wait()


def get_win_env_variable_command(key: str, value: str):
    return f"[Environment]::SetEnvironmentVariable('{key}', '{value}', 'User')"


def add_win_env_variables_command(commands: list):
    powershell_command = "; ".join(commands)
    run_command = subprocess.Popen(
        ["powershell.exe", "-C", powershell_command], shell=False
    )
    run_command.wait()


def update_db_pw_file(
    file_path: str,
    variables: list,
    key_transformer: callable = None,
    value_transformer: callable = None,
):
    if not Path(file_path).exists():
        file = open(file_path, "w")
        file.close()

    with open(file_path, "r+") as config_file:
        config_file_lines = config_file.read().split("\n")

        for variable in variables:
            key, value = variable.split("=", 1)
            if key_transformer:
                key = key_transformer(key)
            if value_transformer:
                value = value_transformer(value)
            config_file_lines = update_list_value_based_on_key(
                config_file_lines, key, value
            )

        config_file.seek(0)
        config_file.write("\n".join(config_file_lines))


def update_config_file(parsed_args, variables_list):
    if parsed_args.win_config is None:
        print("Welp! no path to save config to")
        return

    update_db_pw_file(parsed_args.win_config, variables_list)


def update_bash_file(parsed_args, variables_list):
    if parsed_args.bash_config is None:
        print("Welp! no path to save bash config to")
        return

    update_db_pw_file(
        parsed_args.bash_config,
        variables_list,
        lambda key: f'export "{key}"'.replace("-", ""),
        lambda value: f'"{value}"',
    )


def get_db_token_variable(db_endpoint, rds_client, email):
    token = rds_client.generate_db_auth_token(
        DBHostname=db_endpoint.get("Endpoint"),
        Port=5432,
        DBUsername=email,
    )

    token_key = f"{parsed_args.profile}_{db_endpoint.get('DBClusterIdentifier')}_{db_endpoint.get('EndpointType')}_pw"

    return token_key, token


def connect_to_db(parsed_args):
    print("connecting to db")

    rds_client = parsed_args.boto_client.client("rds")

    sts_client = parsed_args.boto_client.client("sts")
    email = sts_client.get_caller_identity().get("UserId").split(":")[1]

    db_clusters_endpoints = rds_client.describe_db_cluster_endpoints().get(
        "DBClusterEndpoints"
    )

    print(f"Found {len(db_clusters_endpoints)} endpoints")
    bash_variables_list = []
    win_variables_commands_list = []

    # add user to env variables
    user_key = f"{parsed_args.profile}_user"
    win_variables_commands_list.append(get_win_env_variable_command(user_key, email))
    bash_variables_list.append(f"{user_key}={email}")

    tokens = []
    for db_cluster_endpoint in db_clusters_endpoints:
        token_key, token = get_db_token_variable(db_cluster_endpoint, rds_client, email)
        tokens.append((token_key, token))

    for token_key, token in tokens:
        win_variables_commands_list.append(
            get_win_env_variable_command(token_key, token)
        )
        bash_variables_list.append(f"{token_key}={token}")

    start = time.time()
    print(f"adding windows env variables")
    add_win_env_variables_command(win_variables_commands_list)
    end = time.time()
    print(f"Time to add env variables: {round(end - start, 2)} seconds")

    update_config_file(parsed_args, bash_variables_list)
    update_bash_file(parsed_args, bash_variables_list)


def connect_to_env(parsed_args):
    login(parsed_args)
    connect_to_internal_package_managers(parsed_args)
    connect_to_eks(parsed_args)
    connect_to_db(parsed_args)


def reload_modules(parsed_args):
    for module in sys.modules.values():
        if module:
            importlib.reload(module)


def install_vim(profile, region, cluster_name, task_id, container_name):
    # apt-get update
    update_command = f'aws --profile {profile} ecs execute-command --cluster {cluster_name} --region {region} --task {task_id} --container {container_name} --command "apt-get update" --interactive'
    update_process = subprocess.Popen(update_command, shell=True)
    update_process.wait()

    install_vim_command = f'aws --profile {profile} ecs execute-command --cluster {cluster_name} --region {region} --task {task_id} --container {container_name} --command "apt-get install vim -y" --interactive'
    install_vim_process = subprocess.Popen(install_vim_command, shell=True)
    install_vim_process.wait()


def get_cluster_arn(ecs_client):
    clusters = ecs_client.list_clusters()
    clusters_arn = clusters.get("clusterArns")

    cluster = clusters_arn[0]
    if len(clusters) > 1:
        cluster = get_option(
            "cluster", clusters_arn, lambda cluster_arn: cluster_arn.split("/")[-1]
        )

    return cluster


def get_relevant_container(ecs_client, cluster_arn):
    tasks = ecs_client.list_tasks(cluster=cluster_arn)

    tasks_details = ecs_client.describe_tasks(
        cluster=cluster_arn, tasks=tasks.get("taskArns")
    )

    tasks = tasks_details.get("tasks")
    task = tasks[0]
    if len(tasks) > 1:
        task = get_option(
            "task",
            tasks,
            lambda task_details: f'{task_details.get("containers")[0].get("name")}: {task_details.get("taskArn").split("/")[2]}',
        )

    return task.get("containers")[0]


def connect_to_container(parsed_args):
    pprint(parsed_args)

    boto_client = parsed_args.boto_client

    if not is_logged_in(parsed_args):
        login(parsed_args)

    ecs_client = boto_client.client("ecs")

    cluster_arn = get_cluster_arn(ecs_client)

    relevant_container = get_relevant_container(ecs_client, cluster_arn)

    task_arn = relevant_container.get("taskArn").split("/")
    region = task_arn[0].split(":")[3]
    cluster_name = task_arn[1]
    task_id = task_arn[2]

    container_name = relevant_container.get("name")

    install_vim(parsed_args.profile, region, cluster_name, task_id, container_name)

    command = f'aws --profile {parsed_args.profile} ecs execute-command --cluster {cluster_name} --region {region} --task {task_id} --container {container_name} --command "/bin/bash" --interactive'

    print(command)
    try:
        connection_process = subprocess.Popen(command, shell=True)
        connection_process.wait()
    except KeyboardInterrupt:
        print("keyboard interrupt pressed")


def get_secret(secrets_manager_client):
    name_filter = input("Filter secrets by name: ").strip().casefold()

    secrets_list = []
    next_token = True
    while next_token:
        secrets_manager_response = secrets_manager_client.list_secrets(MaxResults=100)
        secrets_list.extend(
            [
                secret
                for secret in secrets_manager_response.get("SecretList")
                if name_filter in secret.get("Name").casefold()
            ]
        )
        next_token = secrets_manager_response.get("NextToken")

    chosen_secret = get_option(
        "secret",
        secrets_list,
        lambda secret: secret.get("Name"),
    )

    secret_response = secrets_manager_client.get_secret_value(
        SecretId=chosen_secret.get("ARN")
    )

    return secret_response


def get_secrets(parsed_args):
    pprint(parsed_args)

    boto_client = parsed_args.boto_client

    if not is_logged_in(parsed_args):
        login(parsed_args)

    secrets_manager_client = boto_client.client("secretsmanager")
    secret_response = get_secret(secrets_manager_client)

    pprint(json.loads(secret_response.get("SecretString")))


def set_secrets(parsed_args):
    pprint(parsed_args)

    boto_client = parsed_args.boto_client

    if not is_logged_in(parsed_args):
        login(parsed_args)

    secrets_manager_client = boto_client.client("secretsmanager")
    secret_response = get_secret(secrets_manager_client)
    secret_value = json.loads(secret_response.get("SecretString"))
    print("current secret:")
    pprint(secret_value)

    additional_values = True
    while additional_values:
        key = input("Key: ").strip()
        value = input("Value: ").strip()

        secret_value[key] = value

        additional_values = input("Add more values? [y/n]").casefold() == "y"

    secrets_manager_client.update_secret(
        SecretId=secret_response.get("ARN"), SecretString=json.dumps(secret_value)
    )
    print(f"Secret {secret_response.get('Name')} updated")


def get_args_parser():
    parser = argparse.ArgumentParser()

    sub_parsers = parser.add_subparsers()

    # login
    login_parser = sub_parsers.add_parser("login")
    login_parser.set_defaults(func=login)

    # connect_to_env
    connect_to_env_parser = sub_parsers.add_parser("connect_to_env")
    connect_to_env_parser.set_defaults(func=connect_to_env)
    connect_to_env_parser.add_argument(
        "--win-config",
        help="config file path to save db credentials on windows for example /mnt/c/Users/gargamel/Documents/Dev/dbeaver_env.txt",
        required=False,
    )
    connect_to_env_parser.add_argument(
        "--bash-config",
        help="config file path to save db credentials on bash for example /users/gargamel/dev/db_env.sh",
        required=False,
    )

    # connect_to_container
    connect_to_container_parser = sub_parsers.add_parser("connect_to_container")
    connect_to_container_parser.set_defaults(func=connect_to_container)

    # get secrets
    secrets_parser = sub_parsers.add_parser("get_secrets")
    secrets_parser.set_defaults(func=get_secrets)

    # set secrets
    secrets_parser = sub_parsers.add_parser("set_secrets")
    secrets_parser.set_defaults(func=set_secrets)

    return parser


if __name__ == "__main__":
    args_parser = get_args_parser()
    parsed_args = args_parser.parse_args()

    parsed_args = setup_basic_env(parsed_args)

    if hasattr(parsed_args, "func"):
        print(f"running {parsed_args.func}")

        # \r is added in windows some times
        profile = get_profile().replace("\r", "")

        parsed_args.profile = profile
        profile_region = get_aws_profile_conf(parsed_args.profile)["region"]
        os.environ["AWS_REGION"] = profile_region

        boto_client = boto3.Session(profile_name=profile, region_name=profile_region)
        parsed_args.boto_client = boto_client

        parsed_args.func(parsed_args)

    else:
        args_parser.print_help()

    print("Done!")
