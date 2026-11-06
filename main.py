"""Okul Zili programını başlatır:  python main.py"""

import sys

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("--version", "--surum"):
        # Kurulum betiği (kur.sh) kurulu sürümü böyle öğrenir: ses sistemi ve pencere başlatılmaz.
        from okul_zili import __version__
        print(__version__)
        sys.exit(0)
    from okul_zili.app import main
    main()
