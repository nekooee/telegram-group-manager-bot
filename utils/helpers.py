def format_file_size(size_bytes: int) -> str:
    """Convert file size to readable format"""
    if size_bytes == 0:
        return "0B"

    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def is_image_file(filename: str) -> bool:
    """Checking if a file is an image or not"""
    if not filename:
        return False

    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
    import os
    file_ext = os.path.splitext(filename.lower())[1]
    return file_ext in image_extensions