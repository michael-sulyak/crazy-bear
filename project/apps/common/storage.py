import datetime
import io
import os
import tempfile

import cv2
import dropbox
import numpy as np
from pandas import DataFrame

from .utils import single_synchronized
from ... import config


class FileStorage:
    _dbx: dropbox.Dropbox

    def __init__(self) -> None:
        self._dbx = dropbox.Dropbox(config.DROPBOX_TOKEN)

    def upload(self, file_name: str, content: bytes) -> None:
        now = datetime.datetime.now()
        file_name = os.path.join('/', now.strftime('%Y-%m-%d'), file_name)
        self._dbx.files_upload(content, file_name)

    def upload_df_as_xlsx(self, file_name: str, data_frame: DataFrame) -> None:
        io_buffer = io.BytesIO()
        data_frame.to_excel(io_buffer)
        io_buffer.seek(0)
        self.upload(file_name=file_name, content=io_buffer.read())

    def upload_frame(self, file_name: str, frame: np.array) -> None:
        is_success, buffer = cv2.imencode('.jpg', frame)
        io_buf = io.BytesIO(buffer)
        self.upload(file_name=file_name, content=io_buf.read())

    def upload_frames_as_video(self, file_name: str, frames: np.array, fps: int) -> None:
        if not frames:
            return

        height, width, layers = frames[0].shape
        size = (width, height,)

        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, 'video.avi')

            video_writer = cv2.VideoWriter(
                filename=filename,
                fourcc=cv2.VideoWriter_fourcc(*'DIVX'),
                fps=fps,
                frameSize=size,
            )

            for frame in frames:
                video_writer.write(frame)

            video_writer.release()

            with open(filename, 'rb') as file:
                self.upload(file_name=file_name, content=file.read())

    @single_synchronized
    def remove_old_folders(self):
        space_usage = self._dbx.users_get_space_usage()
        allocated = space_usage.allocation.get_individual().allocated
        used = space_usage.used / allocated

        if used > 0.9:
            saved_days = 2
        elif used > 0.8:
            saved_days = 3
        elif used > 0.7:
            saved_days = 7
        elif used > 0.6:
            saved_days = 10
        elif used > 0.4:
            saved_days = 14
        else:
            saved_days = 30

        entries = self._dbx.files_list_folder(path='').entries
        entries = sorted(entries, key=lambda x: x.name, reverse=True)[saved_days:]

        for entry in entries:
            self._dbx.files_delete_v2(entry.path_display)


file_storage = FileStorage()
