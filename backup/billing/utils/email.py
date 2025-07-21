from django.core.mail import send_mail

def send_notification(subject, message, recipient):
    send_mail(subject, message, 'your_email@gmail.com', [recipient])
