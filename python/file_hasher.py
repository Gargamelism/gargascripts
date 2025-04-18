import argparse
from progressbar import ProgressBar
from concurrent.futures import ThreadPoolExecutor

from helpers import get_files_in_base_path, calc_file_md5
from sqlite_wrapper import SqliteWrapper

RELEVANT_FILES_TABLE = "relevant_files"
FILES_HASH_TABLE = "file_hashes"


class PathHasher:
    @staticmethod
    def hash_files(files_table, hash_table, db_wrapper: SqliteWrapper):
        page_size = 1000
        total_files = db_wrapper.count(files_table)
        page_count = total_files // page_size + 1

        progress_bar = ProgressBar(max_value=page_count)

        for page in range(page_count):
            page_files = db_wrapper.paginate(files_table, page_size, page)

            def hash_file(file):
                file_md5 = calc_file_md5(file)
                db_wrapper.insert(FILES_HASH_TABLE, [file_md5, file])

            with ThreadPoolExecutor() as executor:
                executor.map(hash_file, [file[0] for file in page_files])

            progress_bar.increment()

        progress_bar.finish()

    @property
    def duplicates(self):
        return self._duplicates_dict


def calc_hashes(base_path, exclude_paths, db_wrapper: SqliteWrapper = None):
    print(f"getting files in {base_path}")
    relevant_files = get_files_in_base_path(
        base_path,
        lambda file_path: not any(exclude_path in file_path for exclude_path in exclude_paths),
    )

    db_wrapper.create_table(RELEVANT_FILES_TABLE, ["path TEXT"])
    db_wrapper.insert_many(RELEVANT_FILES_TABLE, [[file] for file in relevant_files])

    db_wrapper.create_table(FILES_HASH_TABLE, ["md5 TEXT", "path TEXT"])

    print("finding duplicates")
    PathHasher.hash_files(RELEVANT_FILES_TABLE, FILES_HASH_TABLE, db_wrapper)


def main():
    parser = argparse.ArgumentParser(description="calculate all md5 hashes of files in given path recursively")

    parser.add_argument("--base-path", required=True)
    parser.add_argument("--exclude-paths", nargs="+")
    parser.add_argument("--sqlite-db", default="duplicate_files.db")
    args = parser.parse_args()

    db_wrapper = SqliteWrapper(args.sqlite_db)
    try:
        calc_hashes(args.base_path, args.exclude_paths, db_wrapper)
    finally:
        db_wrapper.close()

    print("done!")


if __name__ == "__main__":
    main()
