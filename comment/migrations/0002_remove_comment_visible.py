# Generated by Django 5.0.6 on 2024-07-02 12:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('comment', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='comment',
            name='visible',
        ),
    ]
