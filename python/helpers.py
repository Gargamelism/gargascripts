import os


def change_extension(filename, new_extension):
    return os.path.splitext(filename)[0] + new_extension
