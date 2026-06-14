from __future__ import annotations

from anchor.application.files.models import FileListItem, IndexedFileRecord
from anchor.application.history.models import HistoryListItem, HistoryRecord
from anchor.application.notes.models import NoteListItem, NoteRecord, NoteSearchItem


def compact_note_list_item(note: NoteRecord | NoteListItem | NoteSearchItem) -> NoteListItem:
    if isinstance(note, NoteListItem):
        return note
    return NoteListItem(
        id=note.id,
        project=note.project,
        title=note.title,
        pinned=note.pinned,
        created_at=note.created_at,
    )


def compact_note_search_item(note: NoteRecord | NoteListItem | NoteSearchItem) -> NoteSearchItem:
    if isinstance(note, NoteSearchItem):
        return note
    return NoteSearchItem(
        id=note.id,
        project=note.project,
        title=note.title,
        pinned=note.pinned,
        created_at=note.created_at,
    )


def compact_history_item(history: HistoryRecord | HistoryListItem) -> HistoryListItem:
    if isinstance(history, HistoryListItem):
        return history
    return HistoryListItem(
        id=history.id,
        project=history.project,
        entry_type=history.entry_type,
        actor=history.actor,
        correlation_id=history.correlation_id,
        created_at=history.created_at,
    )


def compact_file_item(file: IndexedFileRecord | FileListItem) -> FileListItem:
    if isinstance(file, FileListItem):
        return file
    return FileListItem(
        id=file.id,
        path=file.path,
        root_path=file.root_path,
        language=file.language,
        file_size=file.file_size,
    )
