"""Which free-trial requests are approved at once (backend/app/trial/auto_approval.py), without a database."""

from backend.app.trial import auto_approval


def test_company_domains_qualify_and_free_mail_reserved_or_odd_domains_do_not():
    for domain in ("acme-medical.com", "devices.co.in", "medtech.example.de"):
        assert auto_approval.is_company_domain(domain), domain
    for domain in ("gmail.com", "outlook.com", "yahoo.co.in", "mailinator.com", "mail.yandex.ru"):
        assert not auto_approval.is_company_domain(domain), domain
    for domain in ("acme.invalid", "acme.test", "intranet.local", "localhost", "10.0.0.1", ""):
        assert not auto_approval.is_company_domain(domain), domain
    assert auto_approval.domain_of("Quality.Lead@Acme-Medical.com") == "acme-medical.com"


def test_it_is_on_by_default_switches_off_and_caps_per_day(monkeypatch):
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE", raising=False)
    assert auto_approval.mode() == "company-domains"
    for value in ("off", "OFF", "false", "manual"):
        monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", value)
        assert auto_approval.mode() == "off"
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", raising=False)
    assert auto_approval.daily_max() == 20
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "5")
    assert auto_approval.daily_max() == 5
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "lots")
    assert auto_approval.daily_max() == 20
