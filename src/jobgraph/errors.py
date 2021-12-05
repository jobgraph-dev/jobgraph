class MissingImageDigest(Exception):
    def __init__(self, image_name, file_location) -> None:
        message = (
            f"Please run `jobgraph update-dependencies` to provide digest "
            f'for {image_name} image on "{file_location}".'
        )
        super().__init__(message)
