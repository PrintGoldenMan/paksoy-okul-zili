import os
import shutil
import subprocess
import tempfile
import unittest

from okul_zili import config, library, sounds


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.mkdtemp()
        self._old = os.environ.get("HOME"), os.environ.get("APPDATA")
        os.environ["HOME"] = os.environ["APPDATA"] = self._home
        library._library = None

    def tearDown(self):
        for key, value in zip(("HOME", "APPDATA"), self._old):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        library._library = None
        shutil.rmtree(self._home, ignore_errors=True)

    def test_long_titles_get_short_safe_file_names(self):
        title = ("İstiklal Marşı (TBMM Resmî Kayıt) | 4K Remastered Official Video — "
                 "Türkiye Büyük Millet Meclisi Korosu ve Orkestrası")
        stem = library.short_file_stem(title, "3fa9c2aa11bb")
        self.assertEqual(stem, "istiklal-marsi-tbmm-resmi-kayit-4k-3fa9c2")
        self.assertLessEqual(len(stem), library.MAX_NAME_CHARS + 7)
        self.assertEqual(library.short_file_stem("???  :<>|", "abcdef123456"), "ses-abcdef")
        self.assertTrue(library.short_title(title).endswith("…"))
        self.assertLessEqual(len(library.short_title(title)), library.MAX_TITLE_CHARS)

    def test_add_resolve_remove(self):
        lib = library.get_library()
        item_id, target = lib.new_target("Zil Sesi")
        target.write_bytes(b"x")
        lib.add(item_id, target, "Zil Sesi", duration=4.2)
        sid = library.PREFIX + item_id
        self.assertEqual(sounds.resolve(sid), target)
        self.assertEqual(sounds.display_name(sid), "Zil Sesi")
        self.assertFalse(sounds.is_missing(sid))
        lib.remove(item_id)
        self.assertIsNone(sounds.resolve(sid))
        self.assertTrue(sounds.is_missing(sid))
        self.assertFalse(target.exists())

    def test_unset_and_silent_sounds(self):
        self.assertTrue(sounds.is_missing(""))
        self.assertFalse(sounds.is_missing(sounds.NO_SOUND))
        self.assertTrue(sounds.is_silent(sounds.NO_SOUND))

    def test_old_builtin_sounds_are_migrated_to_unset(self):
        cfg = config.default_config()
        cfg["bells"]["ogretmen"]["sound"] = "builtin:klasik"
        cfg["extra_bells"] = [{"sound": "builtin:gong"}]
        cfg = config._migrate(cfg)
        self.assertEqual(cfg["bells"]["ogretmen"]["sound"], "")
        self.assertEqual(cfg["extra_bells"][0]["sound"], "")

    def test_import_file_converts_to_opus(self):
        try:
            from okul_zili import downloader
            ffmpeg = downloader.ffmpeg_exe()
        except Exception:  # noqa: BLE001
            self.skipTest("ffmpeg yok")
        src = os.path.join(self._home, "Çok Uzun Bir Dosya Adı – Okul Zili Melodisi (Orijinal Kayıt).wav")
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=44100:cl=mono:d=1.5", "-f", "lavfi", "-i", "sine=frequency=500:duration=3",
                        "-filter_complex", "[0][1]concat=n=2:v=0:a=1", src], check=True)
        item = downloader.import_file(src)
        self.assertTrue(item["file"].endswith(".opus"))
        self.assertRegex(item["file"], r"^cok-uzun-bir-dosya-adi-okul-zili-[0-9a-f]{6}\.opus$")
        # baştaki 1,5 sn sessizlik kırpılmış olmalı
        self.assertAlmostEqual(item["duration"], 3.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()


class SectionTests(unittest.TestCase):
    def test_parse_time_formats(self):
        from okul_zili import downloader as D
        self.assertEqual(D.parse_time("5:30"), 330)
        self.assertEqual(D.parse_time("05:30"), 330)
        self.assertEqual(D.parse_time("1:05:30"), 3930)
        self.assertEqual(D.parse_time("330"), 330)
        self.assertEqual(D.parse_time("5:30,5"), 330.5)
        for bad in ("", "abc", "5:75", "1:2:3:4", "-5", "5::3"):
            with self.assertRaises(D.DownloadError, msg=bad):
                D.parse_time(bad)

    def test_parse_time_rejects_non_numbers_and_accepts_turkish_dot(self):
        from okul_zili import downloader as D
        self.assertEqual(D.parse_time("5.30"), 330)       # Türkçe saat yazımı
        self.assertEqual(D.parse_time("5:30.5"), 330.5)
        for bad in ("inf", "nan", "1e3", "5,30:00"):
            with self.assertRaises(D.DownloadError, msg=bad):
                D.parse_time(bad)
        self.assertEqual(D.fmt_time(59.99), "1:00")
        self.assertEqual(D.fmt_time(0.96), "0:01")

    def test_parse_section_checks(self):
        from okul_zili import downloader as D
        self.assertEqual(D.parse_section("5:30", "5:35"), (330, 335))
        self.assertEqual(D.parse_section("1:25", "1:40", duration=90), (85, 90))   # bitiş sona çekilir
        for start, end in (("5:35", "5:30"), ("5:30", "5:30"), ("2:00", "2:05")):
            with self.assertRaises(D.DownloadError):
                D.parse_section(start, end, duration=90)
        self.assertEqual(D.fmt_time(330), "5:30")
        self.assertEqual(D.fmt_time(3930), "1:05:30")
        self.assertEqual(D.fmt_time(330.5), "5:30,5")


class SectionDownloadTests(unittest.TestCase):
    """Yerel bir web sunucusundan yalnızca seçilen bölümün indirildiğini doğrular."""

    def setUp(self):
        self._home = tempfile.mkdtemp()
        self._old = {k: os.environ.get(k) for k in ("HOME", "APPDATA", "NO_PROXY", "no_proxy")}
        os.environ["HOME"] = os.environ["APPDATA"] = self._home
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        library._library = None

    def tearDown(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        library._library = None
        shutil.rmtree(self._home, ignore_errors=True)

    def test_only_selected_part_is_saved(self):
        try:
            import importlib
            importlib.import_module("yt_dlp")
            from okul_zili import downloader
            ffmpeg = downloader.ffmpeg_exe()
        except Exception:  # noqa: BLE001
            self.skipTest("yt-dlp ya da ffmpeg yok")
        import functools
        import http.server
        import threading
        www = os.path.join(self._home, "www")
        os.makedirs(www)
        # 0–20 sn alçak ton, 20–30 sn yüksek ton, 30–60 sn alçak ton
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "sine=frequency=300:duration=20",
                        "-f", "lavfi", "-i", "sine=frequency=1000:duration=10",
                        "-f", "lavfi", "-i", "sine=frequency=300:duration=30",
                        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1", os.path.join(www, "parca.mp3")],
                       check=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=www)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/parca.mp3"
            item = downloader.download(url, section=downloader.parse_section("0:21", "0:26"))
        finally:
            server.shutdown()
            server.server_close()
        self.assertAlmostEqual(item["duration"], 5.0, delta=0.4)
        self.assertIn("(0:21–0:26)", item["title"])
        self.assertRegex(item["file"], r"^parca-0-21-0-26-[0-9a-f]{6}\.opus$")
        # Kaydedilen bölüm yüksek tonlu kısım olmalı (sıfır geçiş oranı ~0,042; alçak tonda ~0,0125)
        path = str(library.library_dir() / item["file"])
        import re
        out = subprocess.run([ffmpeg, "-hide_banner", "-i", path, "-af", "astats", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        rate = float(re.findall(r"Zero crossings rate: ([0-9.]+)", out)[0])
        self.assertGreater(rate, 0.03)
