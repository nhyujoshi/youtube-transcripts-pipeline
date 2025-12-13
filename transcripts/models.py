# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models
from pgvector.django import VectorField


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

class TextChunks(models.Model):
    """Represents a chunk of transcript text with embedding."""
    id = models.CharField(max_length=255, primary_key=True)
    video = models.ForeignKey('Videos', models.CASCADE, to_field='video_id', db_column='video_id')
    #playlist = models.ForeignKey('Playlists', models.CASCADE, to_field='playlist_id', db_column='playlist_id')
    text = models.TextField()
    start_time_seconds = models.FloatField()
    duration = models.FloatField(null=True, blank=True)
    embedding = VectorField(dimensions=768, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('embedded', 'Embedded'),
            ('error', 'Error'),
        ],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def youtube_timestamp_link(self) -> str:
        """Generate YouTube URL with timestamp."""
        mins = int(self.start_time_seconds // 60)
        secs = int(self.start_time_seconds % 60)
        return f"&t={mins}m{secs}s"

    class Meta:
        managed = True
        db_table = 'text_chunks'
        indexes = [
            models.Index(fields=['video', 'start_time_seconds']),
            models.Index(fields=['status']),
        ]

class Conversation(models.Model):
    """Represents a single conversation session."""
    session_id = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Conversation: {self.session_id}"

class Message(models.Model):
    """Represents a single message within a conversation."""
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=20)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."