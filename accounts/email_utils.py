from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _send_and_record(email, *, recipient, subject, category):
    from .models import NotificationDelivery

    try:
        email.send(fail_silently=False)
    except Exception as exc:
        NotificationDelivery.objects.create(
            category=category,
            recipient=recipient,
            subject=subject,
            status=NotificationDelivery.Status.FAILED,
            error_message=str(exc),
        )
        raise
    NotificationDelivery.objects.create(
        category=category,
        recipient=recipient,
        subject=subject,
        status=NotificationDelivery.Status.SENT,
    )


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


def send_otp_email(*, to_email, code, purpose, cta_url=None):
    is_signup = purpose == "signup"
    is_email_change = purpose == "email_change"
    is_invite = purpose == "invite"
    if is_email_change:
        subject = "Verify your new Siya Real Build email"
        intro = "Use this code to verify and update your Siya Real Build account email."
        badge = "Email Update"
    elif is_invite:
        subject = "Verify your Siya Real Build invite"
        intro = "Use this code to verify your invited email address. Your company owner can approve login access after verification."
        badge = "Invite Verification"
    else:
        subject = "Verify your Siya Real Build signup" if is_signup else "Your Siya Real Build login OTP"
        intro = (
            "Use this code to verify your email and send your signup for admin approval."
            if is_signup
            else "Use this code to login to your approved Siya Real Build account."
        )
        badge = "Signup Verification" if is_signup else "Secure Login"
    title = "Verify new email" if is_email_change else ("Verify invite email" if is_invite else ("Verify your email" if is_signup else "Login verification"))
    text_body = f"{title}\n\n{intro}\n\nYour OTP is {code}. It expires in 10 minutes."
    html_body = render_to_string("emails/notification.html", {
        "badge": badge,
        "code": code,
        "intro": intro,
        "title": title,
        "cta_url": cta_url,
        "cta_link_text": "Verify invite email" if is_invite else "",
    })
    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    email.attach_alternative(html_body, "text/html")
    _attach_logo(email)
    _send_and_record(email, recipient=to_email, subject=subject, category=purpose)



def _send_account_status_email(*, to_email, subject, title, intro, body, badge, cta_text=None, cta_url=None, cta_link_text=None):
    text_body = f"{title}\n\n{intro}\n\n{body}"
    html_body = render_to_string("emails/notification.html", {
        "title": title,
        "intro": intro,
        "body": body,
        "badge": badge,
        "cta_text": cta_text,
        "cta_url": cta_url,
        "cta_link_text": cta_link_text,
    })
    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    email.attach_alternative(html_body, "text/html")
    _attach_logo(email)
    _send_and_record(email, recipient=to_email, subject=subject, category=badge.lower().replace(" ", "_"))


def send_signup_pending_review_email(*, to_email, name):
    first_name = (name or "there").strip().split(" ", 1)[0]
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build signup request is under review",
        title="Signup request received",
        intro=f"Hi {first_name}, your email has been verified and your signup request has been sent to our team.",
        badge="Under Review",
        body=(
            "Our team will verify your details and approve your account if everything is correct. "
            "You will receive another email once the review is complete."
        ),
        cta_text="Our team will verify your request",
    )


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
    )


def send_referral_reward_email(*, to_email, name, reward_amount, coupon_code="", referred_name="", referrer_name="", is_referrer=True):
    first_name = (name or "there").strip().split(" ", 1)[0]
    reward_text = ""
    if reward_amount and reward_amount > 0:
        reward_text = f"Reward amount: Rs. {reward_amount}."
    if coupon_code:
        reward_text = f"{reward_text} Coupon code: {coupon_code}.".strip()
    if not reward_text:
        reward_text = "No reward or coupon has been assigned for this referral."
    if is_referrer:
        intro = f"Hi {first_name}, your referral has been approved as a Channel Partner."
        body = (
            f"{referred_name or 'Your referred contact'} is now active as Channel Partner. "
            f"{reward_text} The reward has been added to your referral record."
        )
    else:
        intro = f"Hi {first_name}, your Channel Partner signup through referral has been approved."
        body = (
            f"You joined using {referrer_name or 'a team member'}'s referral link. "
            f"{reward_text} The reward has been added to your referral record."
        )
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build referral reward is active",
        title="Referral reward active",
        intro=intro,
        badge="Referral Reward",
        body=body,
        cta_text="Reward released after Channel Partner approval",
    )


def send_owner_custom_signup_email(*, to_email, name, subject, message):
    first_name = (name or "there").strip().split(" ", 1)[0]
    _send_account_status_email(
        to_email=to_email,
        subject=subject,
        title=subject,
        intro=f"Hi {first_name}, the Siya Real Build team has sent you an update about your signup request.",
        badge="Owner Message",
        body=message,
        cta_text="Please review this update",
    )


def send_employee_custom_email(*, to_email, name, subject, message, sender_name="Siya Real Build"):
    first_name = (name or "there").strip().split(" ", 1)[0]
    _send_account_status_email(
        to_email=to_email,
        subject=subject,
        title=subject,
        intro=f"Hi {first_name}, {sender_name} has sent you an update.",
        badge="Team Update",
        body=message,
        cta_text="Please review this update",
    )


def send_property_share_email(*, to_email, property_title, property_summary, sender_name="Siya Real Build", property_url=""):
    intro = f"{sender_name} has shared a property listing with you."
    body = property_summary
    _send_account_status_email(
        to_email=to_email,
        subject=f"Property details: {property_title}",
        title=property_title,
        intro=intro,
        badge="Property Details",
        body=body,
        cta_url=property_url or None,
        cta_link_text="Open property details",
    )


def send_meeting_notification_email(*, to_email, name, meeting_title, starts_at, ends_at=None, location="", meeting_link="", description="", action_label="Meeting scheduled"):
    first_name = (name or "there").strip().split(" ", 1)[0]
    details = [f"Meeting: {meeting_title}", f"Starts at: {starts_at}"]
    if ends_at:
        details.append(f"Ends at: {ends_at}")
    if location:
        details.append(f"Location: {location}")
    if meeting_link:
        details.append(f"Meeting link: {meeting_link}")
    if description:
        details.append(f"Notes: {description}")
    _send_account_status_email(
        to_email=to_email,
        subject=f"{action_label}: {meeting_title}",
        title=meeting_title,
        intro=f"Hi {first_name}, a meeting update has been shared with you.",
        badge="Meeting",
        body=" ".join(details),
        cta_text=None if meeting_link else "Please review the meeting details in your dashboard.",
        cta_url=meeting_link or None,
        cta_link_text="Open online meeting",
    )


def send_event_notification_email(*, to_email, name, event_title, starts_at, ends_at=None, caption="", description="", action_label="Event published", audience_label=""):
    first_name = (name or "there").strip().split(" ", 1)[0]
    details = [f"Event: {event_title}", f"Starts at: {starts_at}"]
    if ends_at:
        details.append(f"Ends at: {ends_at}")
    if audience_label:
        details.append(f"Audience: {audience_label}")
    if caption:
        details.append(f"Caption: {caption}")
    if description:
        details.append(f"Details: {description}")
    _send_account_status_email(
        to_email=to_email,
        subject=f"{action_label}: {event_title}",
        title=event_title,
        intro=f"Hi {first_name}, an event update has been shared with you.",
        badge="Event",
        body=" ".join(details),
        cta_text="Please review the event in your dashboard.",
    )


def send_email_updated_email(*, to_email, name, old_email="", new_email="", role_label="", employee_code=""):
    first_name = (name or "there").strip().split(" ", 1)[0]
    details = []
    if new_email:
        details.append(f"New email: {new_email}")
    if old_email:
        details.append(f"Previous email: {old_email}")
    if role_label:
        details.append(f"Role: {role_label}")
    if employee_code:
        details.append(f"Employee code: {employee_code}")
    detail_text = " ".join(details)
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build email has been updated",
        title="Email updated",
        intro=f"Hi {first_name}, your Siya Real Build account email has been updated successfully.",
        badge="Email Updated",
        body=(
            "You can now use this email address for future OTP login and account communication. "
            f"{detail_text} "
            "If you did not request this update, contact the company owner immediately."
        ),
        cta_text="Your email is updated",
    )


def send_role_change_requested_email(*, to_email, name, current_role, requested_role, requester_name="Company owner"):
    first_name = (name or "there").strip().split(" ", 1)[0]
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build role change request is under review",
        title="Role change requested",
        intro=f"Hi {first_name}, {requester_name} has requested a role change for your account.",
        badge="Role Review",
        body=(
            f"Current role: {current_role}. Requested role: {requested_role}. "
            "Your current access remains active until the company owner approves this request."
        ),
        cta_text="Role change is pending review",
    )


def send_role_changed_email(*, to_email, name, old_role, new_role, employee_code="", review_note=""):
    first_name = (name or "there").strip().split(" ", 1)[0]
    details = f"Previous role: {old_role}. New role: {new_role}."
    if employee_code:
        details = f"{details} Employee code: {employee_code}."
    if review_note:
        details = f"{details} Note: {review_note}"
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build role has been updated",
        title="Role updated",
        intro=f"Hi {first_name}, your Siya Real Build access role has been updated.",
        badge="Role Updated",
        body=f"{details} Please sign in again if your dashboard menu does not refresh immediately.",
        cta_text="Your role is updated",
    )


def send_role_change_rejected_email(*, to_email, name, current_role, requested_role, review_note=""):
    first_name = (name or "there").strip().split(" ", 1)[0]
    details = f"Current role: {current_role}. Requested role: {requested_role}."
    if review_note:
        details = f"{details} Note: {review_note}"
    _send_account_status_email(
        to_email=to_email,
        subject="Your Siya Real Build role change request was rejected",
        title="Role change rejected",
        intro=f"Hi {first_name}, your role change request has been reviewed.",
        badge="Role Rejected",
        body=f"{details} Your current account access remains unchanged.",
        cta_text="Role remains unchanged",
    )
