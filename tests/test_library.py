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
