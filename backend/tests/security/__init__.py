"""Saldırı odaklı güvenlik doğrulama paketi (#276).

Her modül bir saldırı sınıfını saldırganın gözünden dener ve savunmanın tuttuğunu kanıtlar.
`scripts/guvenlik_testi.py` bu paketi tek komutla çalıştırıp geçti/kaldı tablosu üretir;
`docs/guvenlik_testi.md` modüllerin OWASP maddeleriyle eşlemesini taşır.
Veritabanı gerektirenler `RUN_DB_TESTS=1` olmadan atlanır (CI'daki duman testi işinde çalışır).
"""
