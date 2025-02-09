#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from sticker_convert.downloaders.download_base import DownloadBase
from sticker_convert.job_option import CredOption
from sticker_convert.utils.callback import CallbackProtocol, CallbackReturn
from sticker_convert.utils.files.metadata_handler import MetadataHandler
from sticker_convert.utils.media.decrypt_kakao import DecryptKakao


def search_bracket(text: str, open_bracket: str = "{", close_bracket: str = "}") -> int:
    depth = 0
    is_str = False

    for count, char in enumerate(text):
        if char == '"':
            is_str = not is_str

        if is_str is False:
            if char == open_bracket:
                depth += 1
            elif char == close_bracket:
                depth -= 1

        if depth == 0:
            return count

    return -1


class MetadataKakao:
    @staticmethod
    def get_info_from_share_link(url: str) -> Tuple[Optional[str], Optional[str]]:
        headers = {"User-Agent": "Android"}

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content.decode("utf-8", "ignore"), "html.parser")

        pack_title_tag = soup.find("title")  # type: ignore
        if not pack_title_tag:
            return None, None

        pack_title: str = pack_title_tag.string  # type: ignore

        app_scheme_link_tag = soup.find("a", id="app_scheme_link")  # type: ignore
        assert isinstance(app_scheme_link_tag, Tag)

        item_code_fake = cast(str, app_scheme_link_tag["data-i"])

        js = ""
        for script_tag in soup.find_all("script"):
            js = script_tag.string
            if js and "emoticonDeepLink" in js:
                break
        if "emoticonDeepLink" not in js:
            return None, None

        func_start_pos = js.find("function emoticonDeepLink(")
        js = js[func_start_pos:]
        bracket_start_pos = js.find("{")
        func_end_pos = search_bracket(js[bracket_start_pos:]) + bracket_start_pos
        js = js[bracket_start_pos + 1 : func_end_pos]
        js = js.split(";")[0]

        minus_num_regex = re.search(r"\-(.*?)\^", js)
        if not minus_num_regex:
            return None, None
        minus_num_str = minus_num_regex.group(1)
        if not minus_num_str.isnumeric():
            return None, None
        minus_num = int(minus_num_str)

        xor_num_regex = re.search(r"\^(.*?)\)", js)
        if not xor_num_regex:
            return None, None
        xor_num_str = xor_num_regex.group(1)
        if not xor_num_str.isnumeric():
            return None, None
        xor_num = int(xor_num_str)

        item_code = str(int(item_code_fake) - minus_num ^ xor_num)

        # https://github.com/Nuitka/Nuitka/issues/385
        # js2py not working if compiled by nuitka
        # web2app_start_pos = js.find("daumtools.web2app(")
        # js = js[:web2app_start_pos] + "return a;}"
        # get_item_code = js2py.eval_js(js)  # type: ignore
        # kakao_scheme_link = cast(
        #     str,
        #     get_item_code(
        #         "kakaotalk://store/emoticon/${i}?referer=share_link", item_code_fake
        #     ),
        # )
        # item_code = urlparse(kakao_scheme_link).path.split("/")[-1]

        return pack_title, item_code

    @staticmethod
    def get_item_code(title_ko: str, auth_token: str) -> Optional[str]:
        headers = {
            "Authorization": auth_token,
        }

        data = {"query": title_ko}

        response = requests.post(
            "https://talk-pilsner.kakao.com/emoticon/item_store/instant_search",
            headers=headers,
            data=data,
        )

        if response.status_code != 200:
            return None

        response_json = json.loads(response.text)
        item_code = response_json["emoticons"][0]["item_code"]

        return item_code

    @staticmethod
    def get_pack_info_unauthed(
        pack_title: str,
    ) -> Optional[dict[str, Any]]:
        pack_meta_r = requests.get(f"https://e.kakao.com/api/v1/items/t/{pack_title}")

        if pack_meta_r.status_code == 200:
            pack_meta = json.loads(pack_meta_r.text)
        else:
            return None

        return pack_meta

    @staticmethod
    def get_pack_info_authed(
        item_code: str, auth_token: str
    ) -> Optional[dict[str, Any]]:
        headers = {
            "Authorization": auth_token,
            "Talk-Agent": "android/10.8.1",
            "Talk-Language": "en",
            "User-Agent": "okhttp/4.10.0",
        }

        response = requests.post(
            f"https://talk-pilsner.kakao.com/emoticon/api/store/v3/items/{item_code}",
            headers=headers,
        )

        if response.status_code != 200:
            return None

        response_json = json.loads(response.text)

        return response_json


class DownloadKakao(DownloadBase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pack_title: Optional[str] = None
        self.author: Optional[str] = None
        self.auth_token: Optional[str] = None

        self.pack_info_unauthed: Optional[dict[str, Any]] = None
        self.pack_info_authed: Optional[dict[str, Any]] = None

    def download_stickers_kakao(self) -> bool:
        self.auth_token = None
        if self.opt_cred:
            self.auth_token = self.opt_cred.kakao_auth_token

        if urlparse(self.url).netloc == "emoticon.kakao.com":
            self.pack_title, item_code = MetadataKakao.get_info_from_share_link(
                self.url
            )

            if item_code:
                return self.download_animated(item_code)
            self.cb.put("Download failed: Cannot download metadata for sticker pack")
            return False

        if self.url.isnumeric() or self.url.startswith("kakaotalk://store/emoticon/"):
            item_code = self.url.replace("kakaotalk://store/emoticon/", "")

            self.pack_title = None
            if self.auth_token:
                self.pack_info_authed = MetadataKakao.get_pack_info_authed(
                    item_code, self.auth_token
                )
                if self.pack_info_authed:
                    self.pack_title = self.pack_info_authed["itemUnitInfo"][0]["title"]
                else:
                    self.cb.put("Warning: Cannot get pack_title with auth_token.")
                    self.cb.put(
                        "Is auth_token invalid / expired? Try to regenerate it."
                    )
                    self.cb.put("Continuing without getting pack_title")

            return self.download_animated(item_code)

        if urlparse(self.url).netloc == "e.kakao.com":
            self.pack_title = urlparse(self.url).path.split("/")[-1]
            self.pack_info_unauthed = MetadataKakao.get_pack_info_unauthed(
                self.pack_title
            )

            if not self.pack_info_unauthed:
                self.cb.put(
                    "Download failed: Cannot download metadata for sticker pack"
                )
                return False

            self.author = self.pack_info_unauthed["result"]["artist"]
            title_ko = self.pack_info_unauthed["result"]["title"]
            thumbnail_urls = self.pack_info_unauthed["result"]["thumbnailUrls"]

            if self.auth_token:
                item_code = MetadataKakao.get_item_code(title_ko, self.auth_token)
                if item_code:
                    return self.download_animated(item_code)
                msg = "Warning: Cannot get item code.\n"
                msg += "Is auth_token invalid / expired? Try to regenerate it.\n"
                msg += "Continue to download static stickers instead?"
                self.cb.put(("ask_bool", (msg,), None))
                if self.cb_return:
                    response = self.cb_return.get_response()
                else:
                    response = False

                if response is False:
                    return False

            return self.download_static(thumbnail_urls)

        self.cb.put("Download failed: Unrecognized URL")
        return False

    def download_static(self, thumbnail_urls: str) -> bool:
        MetadataHandler.set_metadata(
            self.out_dir, title=self.pack_title, author=self.author
        )

        targets: List[Tuple[str, Path]] = []

        for num, url in enumerate(thumbnail_urls):
            dest = Path(self.out_dir, str(num).zfill(3) + ".png")
            targets.append((url, dest))

        self.download_multiple_files(targets)

        return True

    def download_animated(self, item_code: str) -> bool:
        MetadataHandler.set_metadata(
            self.out_dir, title=self.pack_title, author=self.author
        )

        success = self.download_animated_zip(item_code)
        if not success:
            self.cb.put("Trying to download one by one")
            success = self.download_animated_files(item_code)

        return success

    def download_animated_files(self, item_code: str) -> bool:
        play_exts = [".webp", ".gif", ".png", ""]
        play_types = ["emot", "emoji", ""]  # emot = normal; emoji = mini
        play_path_format = None
        sound_exts = [".mp3", ""]
        sound_path_format = None
        stickers_count = 32  # https://emoticonstudio.kakao.com/pages/start

        if not self.pack_info_authed and self.auth_token:
            self.pack_info_authed = MetadataKakao.get_pack_info_authed(
                item_code, self.auth_token
            )
        if self.pack_info_authed:
            preview_data = self.pack_info_authed["itemUnitInfo"][0]["previewData"]
            play_path_format = preview_data["playPathFormat"]
            sound_path_format = preview_data["soundPathFormat"]
            stickers_count = preview_data["num"]
        else:
            if not self.pack_info_unauthed:
                public_url = None
                if urlparse(self.url).netloc == "emoticon.kakao.com":
                    r = requests.get(self.url)
                    # Share url would redirect to public url without headers
                    public_url = r.url
                elif urlparse(self.url).netloc == "e.kakao.com":
                    public_url = self.url
                if public_url:
                    pack_title = urlparse(public_url).path.split("/")[-1]
                    self.pack_info_unauthed = MetadataKakao.get_pack_info_unauthed(
                        pack_title
                    )

            if self.pack_info_unauthed:
                stickers_count = len(self.pack_info_unauthed["result"]["thumbnailUrls"])

        play_type = ""
        play_ext = ""
        if play_path_format is None:
            for play_type, play_ext in itertools.product(play_types, play_exts):
                r = requests.get(
                    f"https://item.kakaocdn.net/dw/{item_code}.{play_type}_001{play_ext}"
                )
                if r.ok:
                    break
            if play_ext == "":
                self.cb.put(f"Failed to determine extension of {item_code}")
                return False
            else:
                play_path_format = f"dw/{item_code}.{play_type}_0##{play_ext}"
        else:
            play_ext = "." + play_path_format.split(".")[-1]

        sound_ext = ""
        if sound_path_format is None:
            for sound_ext in sound_exts:
                r = requests.get(
                    f"https://item.kakaocdn.net/dw/{item_code}.sound_001{sound_ext}"
                )
                if r.ok:
                    break
            if sound_ext != "":
                sound_path_format = f"dw/{item_code}.sound_0##{sound_ext}"
        elif sound_path_format != "":
            sound_ext = "." + sound_path_format.split(".")[-1]

        assert play_path_format
        targets: list[tuple[str, Path]] = []
        for num in range(1, stickers_count + 1):
            play_url = "https://item.kakaocdn.net/" + play_path_format.replace(
                "##", str(num).zfill(2)
            )
            play_dl_path = Path(self.out_dir, str(num).zfill(3) + play_ext)
            targets.append((play_url, play_dl_path))

            if sound_path_format:
                sound_url = "https://item.kakaocdn.net/" + sound_path_format.replace(
                    "##", str(num).zfill(2)
                )
                sound_dl_path = Path(self.out_dir, str(num).zfill(3) + sound_ext)
                targets.append((sound_url, sound_dl_path))

        self.download_multiple_files(targets)

        for target in targets:
            f_path = target[1]
            ext = Path(f_path).suffix

            if ext not in (".gif", ".webp"):
                continue

            with open(f_path, "rb") as f:
                data = f.read()
            data = DecryptKakao.xor_data(data)
            self.cb.put(f"Decrypted {f_path}")
            with open(f_path, "wb+") as f:
                f.write(data)

        self.cb.put(f"Finished getting {item_code}")

        return True

    def download_animated_zip(self, item_code: str) -> bool:
        pack_url = f"http://item.kakaocdn.net/dw/{item_code}.file_pack.zip"

        zip_file = self.download_file(pack_url)
        if zip_file:
            self.cb.put(f"Downloaded {pack_url}")
        else:
            self.cb.put(f"Cannot download {pack_url}")
            return False

        with zipfile.ZipFile(BytesIO(zip_file)) as zf:
            self.cb.put("Unzipping...")
            self.cb.put(
                (
                    "bar",
                    None,
                    {"set_progress_mode": "determinate", "steps": len(zf.namelist())},
                )
            )

            for num, f_path in enumerate(sorted(zf.namelist())):
                ext = Path(f_path).suffix

                if ext in (".gif", ".webp"):
                    data = DecryptKakao.xor_data(zf.read(f_path))
                    self.cb.put(f"Decrypted {f_path}")
                else:
                    data = zf.read(f_path)
                    self.cb.put(f"Read {f_path}")

                out_path = Path(self.out_dir, str(num).zfill(3) + ext)
                with open(out_path, "wb") as f:
                    f.write(data)

                self.cb.put("update_bar")

        self.cb.put(f"Finished getting {pack_url}")

        return True

    @staticmethod
    def start(
        url: str,
        out_dir: Path,
        opt_cred: Optional[CredOption],
        cb: CallbackProtocol,
        cb_return: CallbackReturn,
    ) -> bool:
        downloader = DownloadKakao(url, out_dir, opt_cred, cb, cb_return)
        return downloader.download_stickers_kakao()
