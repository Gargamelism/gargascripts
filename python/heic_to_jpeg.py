import argparse
import os
from PIL import Image
from pillow_heif import register_heif_opener

from helpers import change_extension


def traverse_dir(base_path, cb):
    for root, dirs, files in os.walk(base_path, topdown=True):
        for dir in dirs:
            traverse_dir(os.path.join(root, dir), cb)

        for file in files:
            cb(os.path.join(root, file))


def heic_to_jpg(file_path):
    if file_path.endswith(".heic"):
        print(f"converting {file_path} to jpg")
        my_pic = Image.open(file_path)  # opening .heic images
        jpg_pic_name = change_extension(file_path, ".jpg")
        my_pic.save(jpg_pic_name, format="JPEG", optimize=True, quality=100)


def main():
    parser = argparse.ArgumentParser(
        description="calculate duration times in given file"
    )
    parser.add_argument("base_path")
    args = parser.parse_args()

    register_heif_opener()
    traverse_dir(args.base_path, heic_to_jpg)

    print("done!")


if __name__ == "__main__":
    main()
