# WAN IP Değiştirici — TP-Link TD-W9970

Modemin yönetim arayüzüne giriş yapıp seçilen PPPoE WAN bağlantısını kesen ve
yeniden kuran küçük bir Windows aracı. Amaç: internet servis sağlayıcından
(ISS) yeni bir genel IP almak. İşlem varsayılan olarak **2 dakikada bir**
otomatik tekrarlanır ve **Durdur** düğmesiyle kapatılır.

DSL kullanıcı adı/şifresi değiştirilmez; yalnızca mevcut PPPoE oturumu yenilenir.

## Özellikler

- TP-Link TD-W9970 web arayüzüne RSA ile giriş (harici paket yok)
- WAN bağlantısı seçimi (`dsl_internet` gibi), yanlış bağlantıya dokunmaz
- Kes → bekle → yeniden bağlan → yeni IP'yi doğrula döngüsü
- Başlat / Durdur / tek tur çalıştırma
- Tkinter arayüz, renkli günlük, geri sayım
- Şifre Windows DPAPI ile şifrelenerek `config.json` içinde saklanır
- Hatalı girişte tekrar denemez (modem 5 hatalı denemeden sonra kilitlenir)

## Gereksinimler

- Windows 10/11
- Python 3.8+ (tkinter dahil)
- Modemle aynı ağda olmak
- Modemin yönetici kullanıcı adı ve şifresi

## Kurulum ve kullanım

1. Depoyu indirin veya klonlayın.
2. `Baslat.bat` dosyasına çift tıklayın (veya masaüstü kısayolu).
3. Modem adresi `192.168.1.1`, kullanıcı `admin`, şifre = modem arayüzü şifresi.
4. **Girişi Test Et / Bağlantıları Listele** ile WAN bağlantısını seçin.
5. Aralığı ayarlayıp **Başlat**'a basın.

Pencere açılmazsa `Konsol_Baslat.bat` ile hata mesajını görebilirsiniz.
Ayrıntılı kurulum ve sorun giderme: [OKUBENI.txt](OKUBENI.txt).

## Ayarlar

| Ayar | Varsayılan | Açıklama |
|---|---|---|
| Aralık | 2 dakika | Her turun bitiminden sonra beklenen süre |
| Kesme beklemesi | 6 sn | Bağlantı kesildikten sonra beklenecek süre |
| Bağlanma zaman aşımı | 75 sn | Yeni bağlantı için en uzun bekleme |

## Nasıl çalışır

1. `POST /cgi/getParm` ile RSA ortak anahtarı alınır.
2. Kullanıcı adı ve base64(lenmiş) şifre PKCS#1 v1.5 ile şifrelenip
   `/cgi/login` adresine gönderilir.
3. `POST /cgi?5` ile `WAN_PPP_CONN` listesi okunur.
4. `POST /cgi?7` ile `ACT_PPP_DISCONN` / `ACT_PPP_CONN` komutları gönderilir.
5. Yeni IP, WAN listesi yoklanarak doğrulanır; oturum `/cgi/logout` ile kapatılır.

## Sınırlamalar

- Bazı ISS'ler aynı IP'yi yeniden atar; kesme beklemesini artırmak gerekebilir.
- CGNAT arkasında genel IP değişmeyebilir.
- TP-Link modemler tek yönetici oturumu kabul eder; program çalışırken modem
  arayüzünü başka bir tarayıcıda açık bırakmayın.
- Program modemi yeniden başlatmaz, yalnızca PPPoE oturumunu yeniler.

## Test

```bash
python wan_ip_degistirici.pyw --selftest
python wan_ip_degistirici.pyw --smoke
```

`--selftest` CGI ayrıştırma, RSA/PKCS#1 ve şifre saklama kontrollerini çalıştırır.
