# octopOS - Mimari Tamamlayıcı Notlar (Advanced Considerations)

Bu döküman, `architecture_plan.md` dosyasındaki temel mimariyi güçlendirmek ve kodlama aşamasına geçmeden önce dikkat edilmesi gereken kritik operasyonel detayları içerir.

## 1. Güvenlik ve İzolasyon (Deep-Dive)

Ajanların otonom kod yazıp çalıştırdığı bir sistemde güvenlik, "opsiyonel" değil "zorunluluktur".

- **Network Isolation:** Worker container'lar `--network none` ile başlatılmalı veya sadece AWS API endpointlerine izin veren bir egress firewall (örn: AWS Network Firewall veya Security Group) arkasında tutulmalıdır.
- **Secrets Management:** Ajanların `.env` dosyalarını okuması yerine, `src/utils/aws_utils.py` üzerinden **AWS Secrets Manager** veya **Parameter Store** entegrasyonu ile "runtime-only" yetki alması sağlanmalıdır.
- **Resource Constraints:** Her Docker container için CPU ve RAM limitleri (örn: `mem_limit="512m"`, `cpu_period=100000`) kesinlikle tanımlanmalıdır.

## 2. Maliyet ve Token Kontrolü (Budgeting)

Nova modelleri (özellikle Act ve Pro) yoğun kullanımda maliyetli olabilir.

- **Token Counting:** Her `OctoMessage` alışverişinde kullanılan token miktarı loglanmalı ve bir "Session Budget" (oturum bütçesi) tutulmalıdır.
- **Stop-Loss Mekanizması:** Eğer bir task tahmini 5$ maliyeti aşıyorsa, **Supervisor** işlemi durdurmalı ve kullanıcıdan onay almalıdır.
- **Cache Layer:** Benzer talepler için LLM'e gitmek yerine, LanceDB üzerinde "Semantic Cache" kullanılarak maliyet %30-40 oranında düşürülebilir.

## 3. Gözlemlenebilirlik (Observability & Tracing)

Asenkron ve çok ajanlı sistemlerde hata ayıklama (debugging) kabustur.

- **Trace ID:** Her kullanıcı isteği bir `trace_id` ile başlar. Tüm alt ajan mesajları (OctoMessage) bu ID'yi taşır.
- **Centralized Logging:** Tüm loglar `(timestamp, level, agent_name, trace_id, message)` formatında AWS **CloudWatch**'a gönderilmelidir.
- **State Visualization:** `octo status --trace` komutu ile bir görevin hangi ajanlarda takıldığı görselleştirilmelidir.

## 4. Çoklu Kullanıcı ve Veri İzolasyonu

Eğer sistem Telegram/Slack üzerinden birden fazla kullanıcıya hizmet verecekse:

- **Tenant Isolation:** Her kullanıcının kendi LanceDB tablosu veya namespace'i olmalıdır.
- **Context Switching:** Main Brain, `sender_id` bazlı olarak bellekten doğru profili yüklemelidir.

## 5. Hata Kurtarma (Global Error Recovery)

- **Brain Freeze:** Eğer Main Brain (Orkestratör) beklenmedik bir hata alırsa, sistemin "Safe Mode" (Güvenli Mod) içinde uyanması ve son başarılı state'den devam etmesi (Check-pointing) gerekir.
- **Dead Letter Queue (DLQ):** İşlenemeyen mesajlar bir DLQ'da toplanmalı ve **Self-Healing Agent** bu kuyruğu periyodik olarak analiz etmelidir.

## 6. Geliştirme ve CI/CD Stratejisi

- **Local Mocking:** Geliştirme sırasında maliyeti düşürmek için Bedrock yerine yerel bir `MockBedrock` sınıfı kullanılmalıdır.
- **Agentic Testing:** Sistemin kendi yazdığı `primitives`'ler için otomatik bir "Sandbox Unit Test" katmanı olmalıdır. Testten geçmeyen hiçbir kod `src/primitives/` altına taşınmamalıdır.
