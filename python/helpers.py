import os
import hashlib


def change_extension(filename, new_extension):
    return os.path.splitext(filename)[0] + new_extension


def get_files_in_base_path(base_path, filter_cb=None):
    if filter_cb is None:
        filter_cb = lambda _: True

    relevant_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            file_path = os.path.join(root, file)
            if filter_cb(file_path):
                relevant_files.append(file_path)

    return relevant_files


def calc_file_md5(file_path):
    with open(file_path, "rb") as file:
        file_hash = hashlib.md5()
        while chunk := file.read(8192):
            file_hash.update(chunk)
        return file_hash.hexdigest()
