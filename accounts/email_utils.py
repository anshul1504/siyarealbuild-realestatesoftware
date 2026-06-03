from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _attach_logo(email):
    logo_path = settings.BASE_DIR / "static" / "assets" / "images" / "siya-builder-logo-transparent.png"
    if not logo_path.exists():
        logo_path = settings.BASE_DIR / "static" / "img" / "siya-logo.jpg"
    if logo_path.exists():
        with logo_path.open("rb") as logo_file:
            logo = MIMEImage(logo_file.read())
            logo.add_header("Content-ID", "<siya-logo>")
            logo.add_header("Content-Disposition", "inline", filename=logo_path.name)
            email.attach(logo)


def send_otp_email(*, to_email, code, purpose):
    is_signup = purpose == "signup"
    is_email_change = purpose == "email_change"
    if is_email_change:
        subject = "Verify your new Siya Real Build email"
        intro = "Use this code to verify and update your Siya Real Build account email."
        badge = "Email Update"
    else:
        subject = "Verify your Siya Real Build signup" if is_signup else "Your Siya Real Build login OTP"
        intro = (
            "Use this code to verify your email and send your signup for admin approval."
            if is_signup
            else "Use this code to login to your approved Siya Real Build account."
        )
        badge = "Signup Verification" if is_signup else "Secure Login"
    text_body = f"Your OTP is {code}. It expires in 10 minutes."
    html_body = render_to_string(
        "emails/otp.html",
        {
            "badge": badge,
            "code": code,
            "intro": intro,
            "title": "Verify new email" if is_email_change else ("Verify your email" if is_signup else "Login verification"),
        },
    )
    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    email.attach_alternative(html_body, "text/html")
    _attach_logo(email)
    email.send(fail_silently=False)



def _send_account_status_email(*, to_email, subject, title, intro, body, badge, footer_note, cta_text=None):
    text_body = f"{title}\n\n{intro}\n\n{body}"
    html_body = render_to_string(
        "emails/account_status.html",
        {
            "title": title,
            "intro": intro,
            "body": body,
            "badge": badge,
            "cta_text": cta_text,
            "footer_note": footer_note,
        },
    )
    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    email.attach_alternative(html_body, "text/html")
    _attach_logo(email)
    email.send(fail_silently=False)


def send_signup_approval_confirmation_email(*, to_email, name, role_label):
    first_name = (name or "there").strip().split(" ", 1)[0]
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build signup request is approved",
        title="Signup request approved",
        intro=f"Hi {first_name}, your Siya Real Build signup request has been approved.",
        badge="Approved",
        body=(
            f"Your account is now active with the {role_label} role. "
            "You can sign in using your registered email address and the login OTP sent to your inbox."
        ),
        cta_text="Sign in to continue",
        footer_note="This email was sent after your signup request was approved.",
    )


def send_signup_rejection_email(*, to_email, name, admin_note=""):
    first_name = (name or "there").strip().split(" ", 1)[0]
    body = "Your signup request was reviewed by the Siya Real Build team and could not be approved at this time."
    if admin_note:
        body = f"{body} Note from admin: {admin_note}"
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build signup request was rejected",
        title="Signup request rejected",
        intro=f"Hi {first_name}, your Siya Real Build signup request has been rejected.",
        badge="Rejected",
        body=body,
        cta_text="Please contact the admin team for more details.",
        footer_note="This email was sent after your signup request was reviewed.",
    )


def send_welcome_email(*, to_email, name, role_label):
    first_name = (name or "there").strip().split(" ", 1)[0]
    _send_account_status_email(
        to_email=to_email,
        subject="Welcome to Siya Real Build",
        title="Welcome to Siya Real Build",
        intro=f"Welcome {first_name}, your team workspace is ready.",
        badge="Welcome",
        body=(
            f"You have joined Siya Real Build as {role_label}. "
            "Use your dashboard to manage profile details, company information, team access, and real estate workflow."
        ),
        cta_text="Your account is ready",
        footer_note="This welcome email confirms that your Siya Real Build account is active.",
    )
