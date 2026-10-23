"""Which free-trial requests are approved at once (backend/app/trial/auto_approval.py), without a database."""

from backend.app.trial import auto_approval


def test_company_domains_qualify_and_personal_disposable_reserved_or_odd_domains_do_not():
    for domain in ("acme-medical.com", "devices.co.in", "medtech.example.de"):
        assert auto_approval.is_company_domain(domain), domain
    for domain in ("gmail.com", "outlook.com", "yahoo.co.in", "mailinator.com", "mail.yandex.ru"):
        assert not auto_approval.is_company_domain(domain), domain
    for domain in ("acme.invalid", "acme.test", "intranet.local", "localhost", "10.0.0.1", ""):
        assert not auto_approval.is_company_domain(domain), domain
    assert auto_approval.domain_of("Quality.Lead@Acme-Medical.com") == "acme-medical.com"


def test_each_address_is_a_company_a_personal_a_disposable_or_a_reserved_one():
    kind = auto_approval.mail_kind
    for domain in ("gmail.com", "googlemail.com", "outlook.com", "hotmail.co.uk", "yahoo.co.in", "icloud.com"):
        assert kind(domain) == "personal", domain
    for domain in ("proton.me", "zoho.com", "rediffmail.com", "gmx.de", "fastmail.com", "qq.com"):
        assert kind(domain) == "personal", domain
    for domain in ("mailinator.com", "guerrillamail.com", "sharklasers.com", "10minutemail.com", "yopmail.com"):
        assert kind(domain) == "disposable", domain
    for domain in ("temp-mail.org", "tempmail.com", "trashmail.com", "dispostable.com", "getnada.com", "maildrop.cc"):
        assert kind(domain) == "disposable", domain
    # Subdomains as today: a provider's subdomain is the provider's, a disposable inbox's subdomain is disposable.
    assert kind("mail.yandex.ru") == "personal" and kind("inbox.mailinator.com") == "disposable"
    # A name that only ends like a provider's is a company's.
    assert kind("notgmail.com") == "company" and kind("acme-outlook.com") == "company"
    for domain in ("acme.invalid", "acme.test", "intranet.local", "localhost", "10.0.0.1", ""):
        assert kind(domain) == "reserved", domain
    # Every listed domain is in exactly one list, and none is reserved or a company's.
    assert not auto_approval.PERSONAL_MAIL_DOMAINS & auto_approval.DISPOSABLE_MAIL_DOMAINS
    assert {kind(domain) for domain in auto_approval.PERSONAL_MAIL_DOMAINS} == {"personal"}
    assert {kind(domain) for domain in auto_approval.DISPOSABLE_MAIL_DOMAINS} == {"disposable"}


def test_company_and_personal_is_the_default_and_the_other_modes_still_switch(monkeypatch):
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE", raising=False)
    assert auto_approval.mode() == "company-and-personal"
    for value in ("", "  ", "company-and-personal", "Company-And-Personal"):
        monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", value)
        assert auto_approval.mode() == "company-and-personal", value
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", "company-domains")
    assert auto_approval.mode() == "company-domains"
    # A mistyped value never approves more than company addresses.
    for value in ("company", "company-domain", "all", "on", "true"):
        monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", value)
        assert auto_approval.mode() == "company-domains", value
    for value in ("off", "OFF", "false", "manual"):
        monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", value)
        assert auto_approval.mode() == "off"


def test_company_and_personal_addresses_have_a_daily_cap_each(monkeypatch):
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", raising=False)
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", raising=False)
    assert auto_approval.daily_max() == 20 and auto_approval.personal_daily_max() == 10
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "5")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "3")
    assert auto_approval.daily_max() == 5 and auto_approval.personal_daily_max() == 3
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "0")
    assert auto_approval.personal_daily_max() == 0
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "lots")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "many")
    assert auto_approval.daily_max() == 20 and auto_approval.personal_daily_max() == 10


def test_the_reviewed_list_follows_the_mode(monkeypatch):
    """What a sign-up page opened before 0.10.48 reads as "a person reviews these" (site-info free_mail_domains)."""
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE", raising=False)
    assert auto_approval.reviewed_mail_domains() == sorted(auto_approval.DISPOSABLE_MAIL_DOMAINS)
    everything = sorted(auto_approval.DISPOSABLE_MAIL_DOMAINS | auto_approval.PERSONAL_MAIL_DOMAINS)
    for value in ("company-domains", "off"):
        monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", value)
        assert auto_approval.reviewed_mail_domains() == everything
