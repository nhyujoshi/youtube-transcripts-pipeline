# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class TranscriptEnrichments(models.Model):
    video = models.ForeignKey('Videos', models.DO_NOTHING, to_field='video_id')
    language = models.CharField(max_length=10, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'transcript_enrichments'


class Transcripts(models.Model):
    video = models.ForeignKey('Videos', models.DO_NOTHING, to_field='video_id')
    text = models.TextField()
    start_time = models.FloatField(blank=True, null=True)
    duration = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'transcripts'


class Videos(models.Model):
    video_id = models.CharField(unique=True, max_length=255)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'videos'