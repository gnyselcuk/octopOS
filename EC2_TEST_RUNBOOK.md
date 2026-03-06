# 🐙 octopOS - EC2 Production Test Runbook

Bu belge, octopOS'un temiz bir Amazon EC2 sunucusu üzerinde baştan sona tüm yeteneklerinin test edilmesi için hazırlanmış resmi test senaryosudur.

## 🏗️ Aşama 1: Kurulum ve Ortam (Environment)

**1. Sunucu Hazırlığı:**

- Ubuntu 22.04 LTS tabanlı bir EC2 instance başlat (önerilen: `t3.small` veya `t3.medium`).
- Instance'a bir IAM Role bağla. Bu rol şu yetkilere sahip olmalı:
  - `AmazonBedrockFullAccess`
  - `AmazonS3FullAccess` (octopos-artifacts bucket'ı için)
  - `AmazonDynamoDBFullAccess` (opsiyonel, memory için konfigüre edilecekse)
- Sunucuya SSH ile bağlan.

**2. Kurulum Adımları:**

```bash
# Repo'yu klonla veya kopyala
git clone https://github.com/octopos/octopos.git
cd octopos

# Test scriptini çalıştırarak bağımlılıkları yükle (Bu script her şeyi kuracaktır)
bash scripts/test_fresh_install.sh

# PATH ayarını yap (kalıcı olması için)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**3. Konfigürasyon:**

```bash
# Setup sihirbazını başlat
octo setup
```

*(AWS Profile kısmını boş geçebilirsin, EC2 IAM rolünü otomatik tanıyacaktır. Telegram Token'ı gir.)*

---

## 🧪 Aşama 2: Core (Çekirdek) Özellik Testleri

**Test 2.1: CLI Sağlamlık Kontrolü**

```bash
octo agent-status
octo budget
```

✅ **Beklenen:** Ajanların durumu (PENDING/IDLE) ve harcanan token bütçesinin (Sıfır veya çok düşük) ekrana düzgün bir tablo ile basılması.

**Test 2.2: Standart Chat ve Bellek (LanceDB)**

```bash
octo chat
```

1. `"Merhaba, benim adım Selocan, projeyi test ediyorum."` yaz.
2. Ajanın cevap vermesini bekle.
3. `/exit` yazarak çık.
4. Tekrar `octo chat` yazıp gir.
5. `"Benim adım neydi ve şu an ne yapıyoruz?"` diye sor.
✅ **Beklenen:** Ajanın önceki konuşmayı (Selocan, test yapıyoruz) hatırlaması. (Episodic memory testi).

---

## 🌐 Aşama 3: Araç (Primitive) ve Sandbox Testi

**Test 3.1: Kod Üretimi ve S3 Teslimatı**

```bash
octo chat
```

1. Sisteme şunu yaz: `"Bana 1 ile 100 arasında rastgele sayı üreten bir python fonksiyonu yazıp kaydeder misin?"`
✅ **Beklenen:**

- CoderAgent'ın devreye girmesi.
- Kodu yazıp Supervisor'a onaylatması.
- Sandbox (Docker veya Subprocess) içinde kodu test edip geçirmesi.
- **S3'e upload edip ekrana tıklanabilir bir Presigned URL vermesi (24 saat geçerli).**

---

## 🤖 Aşama 4: Web Otomasyonu (Nova Act) Testi

**Test 4.1: Başarısız/Başarılı Web Araması**

```bash
octo browse "https://news.ycombinator.com" --headless
```

✅ **Beklenen:**

- Ajanın siteye gitmesi, başlıkları okuması (headless modda).
- Sayfanın DOM yapısını özetleyip CLI ekranına loglaması.

---

## 📱 Aşama 5: Telegram Entegrasyon Testi

**Test 5.1: Mesajlaşma ve Dosya Teslimi**

1. EC2 üzerinde Telegram Botunu ayağa kaldır (şu an için `.env` bazlı veya script ile çalışıyorsa arka planda başlat).
   *(Not: Bot çalıştırma komutu projenin ana yapısına göre `python3 src/interfaces/telegram/bot.py` vs. olabilir.)*
2. Kendi telefonundan bota yaz: `"Merhaba, nasılsın?"`
✅ **Beklenen:** Ajanın sana Telegram'dan yanıt vermesi.

**Test 5.2: Telegram Üzerinden İşlem**

1. Bota yaz: `"Bana basit bir HTML login sayfası kodu yazar mısın?"`
✅ **Beklenen:**

- Ajanın kodu üretmesi.
- S3'e yüklemesi.
- Sana Telegram üzerinden **Dosya (Document)** olarak göndermesi ve altında `S3 İndirme Linki` olan bir açıklama (caption) yazması.

---

## 🎤 Aşama 6: Ses (Nova Sonic) Testi

*Not: EC2'de mikrafon olmadığı için bu testin CLI parametreleriyle çalışması gerekir.*

**Test 6.1: Text-to-Speech (Sadece Çıktı)**
Eğer EC2 üzerinde hoparlör/mikrofon yoksa, fallback mekanizmasını test et:

```bash
octo voice
```

✅ **Beklenen:**

- Mikrafon bulunamadığı için sistemin Graceful Degradation (zarif düşüş) yaparak kapanması veya ekrana "Ses donanımı bulunamadı" logunu basması. Bedrock stream hatası atmaması gerekir.

---

## 🏁 Sonuç ve Kontrol Listesi

- [ ] Tüm AWS IAM Yetkileri doğru çalıştı mı?
- [ ] Pytest ve fresh_install scripti hatasız bitti mi?
- [ ] LanceDB state verilerini tutup hatırladı mı?
- [ ] Sandbox izole ortamda kod çalıştırabildi mi?
- [ ] Telegram üzerinden S3 presigned URL'si olan bir dosya ulaştı mı?

Eğer hepsi evetse: **Tebrikler, octopOS Production Ready! 🚀**
