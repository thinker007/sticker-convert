#!/usr/bin/env python3
import copy
import shutil
import zipfile
from multiprocessing.managers import BaseProxy
from pathlib import Path
from typing import Optional, Union

from sticker_convert.converter import StickerConvert  # type: ignore
from sticker_convert.job_option import (CompOption, CredOption,  # type: ignore
                                        OutputOption)
from sticker_convert.uploaders.upload_base import UploadBase  # type: ignore
from sticker_convert.utils.callback import Callback, CallbackReturn  # type: ignore
from sticker_convert.utils.files.cache_store import CacheStore  # type: ignore
from sticker_convert.utils.files.metadata_handler import MetadataHandler  # type: ignore
from sticker_convert.utils.files.sanitize_filename import sanitize_filename  # type: ignore
from sticker_convert.utils.media.codec_info import CodecInfo  # type: ignore
from sticker_convert.utils.media.format_verify import FormatVerify  # type: ignore


class CompressWastickers(UploadBase):
    def __init__(self, *args, **kwargs):
        super(CompressWastickers, self).__init__(*args, **kwargs)
        base_spec = CompOption({
            "size_max": {"img": 100000, "vid": 500000},
            "res": 512,
            "duration": {"min": 8, "max": 10000},
            "format": ".webp",
            "square": True,
        })

        self.spec_cover = CompOption({
            "size_max": {"img": 50000, "vid": 50000},
            "res": 96,
            "fps": 0,
            "format": ".png",
            "animated": False,
        })

        self.webp_spec = copy.deepcopy(base_spec)
        self.webp_spec.format = ".webp"
        self.webp_spec.animated = None if self.opt_comp.fake_vid else True

        self.png_spec = copy.deepcopy(base_spec)
        self.png_spec.format = ".png"
        self.png_spec.animated = False

        self.opt_comp_merged = copy.deepcopy(self.opt_comp)
        self.opt_comp_merged.merge(base_spec)

    def compress_wastickers(self) -> list[str]:
        urls = []
        title, author, emoji_dict = MetadataHandler.get_metadata(
            self.opt_output.dir,
            title=self.opt_output.title,
            author=self.opt_output.author,
        )
        packs = MetadataHandler.split_sticker_packs(
            self.opt_output.dir,
            title=title,
            file_per_pack=30,
            separate_image_anim=not self.opt_comp.fake_vid,
        )

        for pack_title, stickers in packs.items():
            # Originally the Sticker Maker application name the files with int(time.time())
            with CacheStore.get_cache_store(
                path=self.opt_comp.cache_dir
            ) as tempdir:
                for num, src in enumerate(stickers):
                    self.cb.put(f"Verifying {src} for compressing into .wastickers")

                    if self.opt_comp.fake_vid or CodecInfo.is_anim(src):
                        ext = ".webp"
                    else:
                        ext = ".png"

                    dst = Path(tempdir, str(num) + ext)

                    if (FormatVerify.check_file(src, spec=self.webp_spec) or
                        FormatVerify.check_file(src, spec=self.png_spec)):
                        shutil.copy(src, dst)
                    else:
                        StickerConvert.convert(Path(src), Path(dst), self.opt_comp_merged, self.cb, self.cb_return)

                out_f = Path(self.opt_output.dir, sanitize_filename(pack_title + ".wastickers")).as_posix()

                self.add_metadata(tempdir, pack_title, author)
                with zipfile.ZipFile(out_f, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for file in tempdir.iterdir():
                        file_path = Path(tempdir, file)
                        zipf.write(file_path, arcname=file_path.stem)

            self.cb.put((out_f))
            urls.append(out_f)

        return urls

    def add_metadata(self, pack_dir: Path, title: str, author: str):
        opt_comp_merged = copy.deepcopy(self.opt_comp)
        opt_comp_merged.merge(self.spec_cover)

        cover_path_old = MetadataHandler.get_cover(self.opt_output.dir)
        cover_path_new = Path(pack_dir, "100.png")
        if cover_path_old:
            if FormatVerify.check_file(cover_path_old, spec=self.spec_cover):
                shutil.copy(cover_path_old, cover_path_new)
            else:
                StickerConvert.convert(
                    cover_path_old, cover_path_new, opt_comp_merged, self.cb, self.cb_return
                )
        else:
            # First image in the directory, extracting first frame
            first_image = [
                i
                for i in sorted(self.opt_output.dir.iterdir())
                if Path(self.opt_output.dir, i).is_file()
                and not i.endswith((".txt", ".m4a", ".wastickers"))
            ][0]
            StickerConvert.convert(
                Path(self.opt_output.dir, first_image),
                cover_path_new,
                opt_comp_merged,
                self.cb,
                self.cb_return,
            )

        MetadataHandler.set_metadata(pack_dir, author=author, title=title)

    @staticmethod
    def start(
        opt_output: OutputOption,
        opt_comp: CompOption,
        opt_cred: CredOption,
        cb: Union[BaseProxy, Callback, None] = None,
        cb_return: Optional[CallbackReturn] = None
    ) -> list[str]:
        exporter = CompressWastickers(
            opt_output,
            opt_comp,
            opt_cred,
            cb,
            cb_return
        )
        return exporter.compress_wastickers()
