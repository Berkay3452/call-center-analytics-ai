"""Multi-agent analiz katmanı.

Ajanlar (mimari dokümanı §5.3): Triage, Özet, Duygu/Niyet, Anahtar Kelime/Konu, Şikayet Tespit.
Orkestratör önce sıralı (v1), sonra LangGraph (v2) olarak yazılacak. Tüm ajanlar
`base.BaseAgent` sözleşmesini uygular; böylece LangGraph'a geçişte ajan kodu değişmez.
"""
