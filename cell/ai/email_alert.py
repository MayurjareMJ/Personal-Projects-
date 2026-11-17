import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


# subject="Test Mail",
# body="This is a test email from Python module.",
# to_email=["krishnak@elansoltech.com","tejasg@elansoltech.com","jayr@elansoltech.com"],
# sender_email="elansol.mail.sender@gmail.com",
# sender_password="ebqz rpvu mxqc xbav",
# attachment_path=None


def send_email(subject, body, to_email, sender_email, sender_password, attachment_path=None):
    """
    Send an email with optional attachment using Gmail SMTP.

    Args:
        subject (str): Email subject
        body (str): Email body text
        to_email (str or list): Recipient email(s)
        sender_email (str): Sender Gmail address
        sender_password (str): Sender Gmail password or app password
        attachment_path (str, optional): Path to file to attach
    """

    smtp_server = 'smtp.gmail.com'
    smtp_port = 587

    # Ensure recipients is a list
    if isinstance(to_email, str):
        to_email = [to_email]

    # Create the MIME message
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = ", ".join(to_email)
    message['Subject'] = subject

    # Attach body text
    message.attach(MIMEText(body, 'plain'))

    # Attach file if provided
    if attachment_path:
        with open(attachment_path, 'rb') as attachment:
            base = MIMEBase('application', 'octet-stream')
            base.set_payload(attachment.read())
        encoders.encode_base64(base)
        base.add_header(
            'Content-Disposition',
            f'attachment; filename="{attachment_path.split("/")[-1]}"'
        )
        message.attach(base)

    # Send email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, message.as_string())


# Example usage (remove when using as a module):
if __name__ == "__main__":
    send_email(
        subject="Test Mail",
        body="This is a test email from Python module.",
        to_email=["krishnak@elansoltech.com","tejasg@elansoltech.com","jayr@elansoltech.com"],
        sender_email="elansol.mail.sender@gmail.com",
        sender_password="ebqz rpvu mxqc xbav",
        attachment_path=None
    )
