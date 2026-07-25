# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Not: Bu projede iletişim ve kod yorumları Türkçedir. Kod tanımlayıcıları (değişken,
> fonksiyon adları vb.) İngilizce/orijinal halindedir.

## Proje Nedir

Spoty, tek kullanıcı (kişisel) için bir masaüstü müzik uygulamasıdır: internetten şarkı
**arayıp indirir** (yt-dlp + ffmpeg) ve indirilenleri **Spotify benzeri bir arayüzde çalar**.
İndirilen mp3'lere albüm kapağı ve şarki/sanatçı etiketi gömülür. Çalma listeleri ve
kütüphane SQLite'ta tutulur.

Arayüz **HTML/CSS/JS** olarak yazılmış ve **pywebview + WebView2** ile bir masaüstü
penceresinde gösterilir (tasarım mockup'ına piksel-mükemmel uyar). Tüm uygulama mantığı
ve ses Python'dadır; webview yalnız görünüm + kullanıcı girdisidir.

## Komutlar

Tüm komutlar **proje kökünden** çalıştırılmalıdır (aksi halde `spoty` paketi bulunamaz).
Sanal ortam Python'u doğrudan çağrılır:

```powershell
# Uygulamayı çalıştır
.\.venv\Scripts\python.exe -m spoty.webmain

# Bağımlılıkları kur (gerekirse)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Her çekirdek modülün kendi terminal self-test'i vardir (`__main__`); arayüz olmadan
parça parça test etmek için kullanılır:

```powershell
# Arama + indirme: arama terimi VEYA link (TikTok/YouTube) verilebilir
.\.venv\Scripts\python.exe -m spoty.core.downloader "tarkan kuzu kuzu"
.\.venv\Scripts\python.exe -m spoty.core.downloader "https://www.tiktok.com/@.../video/..."

# Video indirme (mp4, en iyi kalite -> video/ klasoru). Yalnizca link ile calisir.
.\.venv\Scripts\python.exe -m spoty.core.downloader --video "https://www.youtube.com/watch?v=..."

# Çalma: music/ içindeki ilk mp3'ü (veya verilen dosyayı) çalar ve kontrolleri test eder
.\.venv\Scripts\python.exe -m spoty.core.player

# Kütüphane: SQLite ekle/dedup/çalma listesi akışını test eder
.\.venv\Scripts\python.exe -m spoty.core.library
```

Notlar:
- **ffmpeg** harici bir gereksinimdir (winget `Gyan.FFmpeg` ile kuruldu). PATH'te
  olmasa bile `config.find_ffmpeg_dir()` onu winget'in `WinGet\Links` konumundan bulur.
- ⚠️ **Python, Microsoft Store'dan kurulu OLMAMALI.** Store Python paketli (MSIX) çalışır;
  Windows pencerenin görev çubuğu kimliğini paketten alır ve uygulamanın bildirdiği
  `AppUserModelID`'yi yok sayar → uygulama hep "Python" ikonuyla görünür, sabitlenen
  kısayolla eşleşmez. Bu venv **python.org** sürümüyle kuruludur
  (`%LOCALAPPDATA%\Programs\Python\Python313`). Kontrol:
  `.\.venv\Scripts\python.exe -c "import sys; print(sys.base_prefix)"` — çıktıda
  `WindowsApps` geçmemeli. Geçiyorsa venv'i python.org sürümüyle yeniden oluştur.
- **Görev çubuğu kimliği:** `spoty/webmain.py` → `APP_ID = "Ulger.Spoty"`; kısayol da aynı
  kimliği taşımalı → `tools/fix_shortcut.ps1` (kısayolu oluşturur + kimliği yazar).
- **deno** harici bir gereksinimdir (winget `DenoLand.Deno`, 2026-07-25'te kuruldu).
  yt-dlp'nin YouTube çıkarıcısı bir JavaScript çalıştırıcısı ister; yoksa
  "No supported JavaScript runtime" uyarısı verir ve **bazı formatları hiç göremez**
  (yani "en iyi kalite" gerçekte en iyi olmayabilir). Hem mp3 hem mp4 indirmeyi etkiler.
- **WebView2 Runtime** sistemde kurulu olmalı (Windows 11'de genelde vardır). pywebview
  Windows'ta `pythonnet` ile EdgeChromium backend'ini kullanır.
- Türkçe karakterler için `_cli()` fonksiyonları stdout'u UTF-8'e ayarlar; düz script
  çalıştırırken `PYTHONUTF8=1` ortam değişkeni yardımcı olur.
- Resmî bir test paketi (pytest) yoktur; doğrulama, modüllerin `__main__` self-test'leri,
  `Api()` üstünden GUI'siz çağrılar ve uygulamayı çalıştırıp gözle bakarak yapılır.

## Mimari (Büyük Resim)

İki katman: **`spoty/core/`** (arayüzden tamamen bağımsız servisler) ve **webview arayüzü**
(`spoty/web_app.py` + `spoty/webmain.py` + `spoty/web/`). Bu ayrım sayesinde her çekirdek
modül tek başına (terminalden) test edilebilir; arayüz bunları bir köprü üzerinden bağlar.

### Yapılandırma (`spoty/config.py` — paket kökünde, `core/` altında DEĞİL)
- **`config.py`** — tüm yolların tek kaynağı (`MUSIC_DIR`, `VIDEO_DIR`, `DATA_DIR`, `DB_PATH`),
  indirme sabitleri (`AUDIO_FORMAT`=mp3, `AUDIO_QUALITY`=192, `SEARCH_LIMIT`,
  `VIDEO_FORMAT`=`bv*+ba/b`, `VIDEO_CONTAINER`=mp4) ve `find_ffmpeg_dir()`.
  Import edilince `music/`, `video/` ve `data/` klasörlerini oluşturur.
  Hem `core/` hem `web_app.py` buradan import eder.

### Çekirdek servisler (`spoty/core/`)
- **`downloader.py`** — yt-dlp sarmalayıcı. `search()` hız için `extract_flat` kullanır.
  Asıl indirme **`download_from_url(url)`** yapar (TikTok/YouTube/herhangi desteklenen
  site); `download(result)` arama sonucu için bunu çağırıp eksik alanları tamamlar.
  Postprocessor zinciri (ffmpeg): `FFmpegExtractAudio`(mp3) → `FFmpegMetadata` →
  `EmbedThumbnail`. **Kapak ve etiketler indirme anında mp3 içine gömülür.**
  **Video indirme ayrı yoldur:** `download_video_from_url(url)` → `video/` klasörüne
  mp4. Format `bv*+ba/b` (en iyi görüntü + en iyi ses ayrı iner, ffmpeg **birleştirir**)
  ve `merge_output_format=mp4` + `FFmpegVideoRemuxer`. Hepsi **stream copy** — yeniden
  kodlama YOK, dolayısıyla kalite kaybı yok. Dönen `DownloadedVideo.ext` gerçek uzantıyı
  söyler: nadiren bir kodek mp4'e remux edilemezse dosya .mkv/.webm kalır.
  **Video kütüphaneye EKLENMEZ** (`player` yalnız ses çalar).
  ⚠️ İnen mp4'ün içi genelde **AV1 + Opus** olur; PC'de sorunsuz, ama eski oynatıcı/TV/
  WhatsApp'ta açılmayabilir. "Her yerde açılsın" istenirse format seçicisi H.264+AAC'ye
  daraltılmalı (kalite tavanı ~1080p'ye iner).
- **`player.py`** — `just_playback.Playback` üstünde `Player` sınıfı. **Lazy-init**:
  alttaki çalıcı yalnızca ilk `load()`'da oluşur, böylece modülü import etmek ses aygıtı
  gerektirmez. `has_ended()` doğal bitişi tespit eder (otomatik "sonraki şarkı" için);
  duraklatma aktif sayılır, bitiş sayılmaz.
- **`library.py`** — stdlib `sqlite3`. Tablolar: `tracks` (`filepath` UNIQUE → aynı dosya
  ciftlenmez), `playlists` (`name` UNIQUE), `playlist_tracks` (çift PK + `position`, FK
  `ON DELETE CASCADE`). `init_db()` import'ta çağrılır; her bağlantıda `PRAGMA
  foreign_keys = ON`. `yt_dlp` import'undan kaçınmak için `DownloadedTrack` yalnızca
  `TYPE_CHECKING` altında. Sıralama `reorder_playlist`, dedup/yeniden adlandırma vb. burada.
- **`metadata.py`** — mp3'teki gömülü kapağı (ID3 APIC) `PIL.Image` olarak okur. Arayüz
  bunu base64 JPEG data-URI'ye çevirip JS'e verir (`web_app._cover_uri`).
- **`settings.py`** — `data/settings.json` (`volume`, `last_track_id`) — kapat/aç arası
  hatırlanan küçük durum.

### Arayüz — Webview (`spoty/web_app.py` + `spoty/webmain.py` + `spoty/web/`)
Mockup'a (claude.ai tasarımı) **piksel-mükemmel** uymak için arayüz HTML/CSS/JS olarak
yazıldı ve **pywebview + WebView2 (EdgeChromium)** ile gösterilir. Ses YİNE Python'da
(`just_playback`) çalar — webview yalnız görünüm + girdi.
- **`webmain.py`** — giriş (`python -m spoty.webmain`). `webview.create_window(..., js_api=Api())`
  ile `web/index.html`'i yükler; kapanışta `api.save_state` (ses + son şarkı).
- **`web_app.py` → `Api`** — JS'in `window.pywebview.api.<metot>(...)` ile çağırdığı köprü;
  Promise döner. Çalma kuyruğu/shuffle/repeat burada. Önemli metotlar:
  `get_initial/get_library/get_playlists/get_playlist_tracks`, `play/toggle/next/prev/seek/
  set_volume/set_shuffle/set_repeat`, `progress` (JS ~300ms yoklar, doğal bitişte sonrakine
  geçer), `search/download` (tek ağ-gerektiren kısım), `create_playlist/add_to_playlist/
  remove_from_playlist/playlists_for_track/rename_track/delete_track/reorder_playlist`,
  ayrıca `download_video` (mp4 → `video/`, kütüphaneye eklemez), `download_progress`
  (indirme sürerken JS ~500ms yoklar; yt-dlp hook'ları ayrı thread'den `self._dl`
  sözlüğünü günceller — `progress_hooks` indirme yüzdesi, `postprocessor_hooks`
  ffmpeg aşaması) ve `open_video_folder` (`os.startfile` — yalnız gerçek uygulamada
  çalışır, tarayıcıda test edilemez).
  Kapaklar **base64 JPEG data-URI** (`_cover_uri`, önbellekli); liste karo renkleri `_tile()`
  (ada göre deterministik renk paleti).
- **`web/index.html` / `style.css` / `app.js` / `icons.js`** — CSS değişkenleri = mockup
  renkleri. İlerleme/ses çubukları **özel `<div>`** (ince çubuk + dolgu + yuvarlak tutamak →
  piksel-mükemmel). İkonlar inline SVG (`icons.js`). Diyaloglar HTML modal (`#overlay`).
  Sürükle-bırak HTML5 DnD (`enableDrag`). Arama sonuçları arama çubuğu altında **açılır panel**
  (`#searchPanel`); yükleniyor durumları **CSS spinner** (metin yok). Her sonuç satırında
  **iki indirme düğmesi**: `.dl` (dolu yeşil = mp3, kütüphaneye) ve `.dlv` (mp4 → `video/`).
  Arama kutusuna **link yapıştırılınca** doğrudan inmez; `renderLinkChoice()` tek satırlık
  mp3/mp4 seçimi gösterir. Bildirimler `#status` **durum çubuğu** ile verilir —
  `setStatus(mesaj, {kind:'ok'|'error', action, onAction})`, player bar'ın üstünde yüzer,
  4/8/9 sn sonra kendiliğinden kaybolur (mesaj `esc()` ile kaçırılır). Çalma `app.js`'te bir
  kuyruk üzerinden değil, `Api`'deki kuyruk üzerinden yürür; JS yalnız komut yollar.
- **Yeni özellik ekleme deseni**: `Api`'ye metot yaz → `app.js`'te `await API.<metot>(...)`.
  Uzun/ağ işleri (search/download) pywebview tarafından ayrı thread'de koşar, UI'yı bloklamaz.
- Tasarım referansı: `design/mockup.html` (claude.ai çıktısının çözülmüş hali).

### Veri akışı (tipik)
arama → `Api.search` → `downloader.search` → açılır panelde sonuçlar → İndir →
`Api.download` → `downloader.download_from_url` → `library.add_track` → `Api.get_library` →
liste yeniden çizilir → ▶ tıkla → `Api.play` → `player.load/play` → `Api._now_dict`
(başlık + base64 kapak) → JS şimdi-çalan barı/panelini günceller. İlerleme `Api.progress`
yoklamasıyla akar.

## Test etme

Otomatik GUI testi yok; görsel doğrulama uygulamayı çalıştırarak yapılır
(`python -m spoty.webmain`). Mantık katmanı GUI'siz test edilebilir: `from spoty.web_app
import Api; a = Api()` kurup metotları (`get_library`, `play`, `create_playlist`, ...)
doğrudan çağır — webview gerektirmez. Çekirdek modüllerin kendi `__main__` self-test'leri
vardır (yukarıdaki komutlar). `app.js`/`icons.js` için `node --check <dosya>` ile sözdizimi
denetlenebilir.
