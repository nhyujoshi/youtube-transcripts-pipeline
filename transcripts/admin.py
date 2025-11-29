from django.contrib import admin
from .models import Videos, Transcripts, TranscriptEnrichments

# Register your models here.
@admin.register(Videos)
class VideosAdmin(admin.ModelAdmin):
    list_display = ('video_id', 'created_at')
    search_fields = ('video_id',)

@admin.register(Transcripts)
class TranscriptsAdmin(admin.ModelAdmin):
    list_display = ('video', 'start_time', 'duration', 'display_text_preview')
    list_filter = ('video',)
    search_fields = ('text',)
    ordering = ('video', 'start_time')
    
    def display_text_preview(self, obj):
        return obj.text[:80] + '...' if obj.text and len(obj.text) > 80 else obj.text
    display_text_preview.short_description = 'Text Preview'

@admin.register(TranscriptEnrichments)
class TranscriptEnrichmentsAdmin(admin.ModelAdmin):
    list_display = ('video', 'language', 'created_at')
    list_filter = ('language', 'created_at')