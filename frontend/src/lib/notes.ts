import { api, type UserNote } from "@/lib/api";

export type Note = UserNote;
export const loadNotes = () => api.notes();
export const addNote = (kind: string, title: string, content: string) =>
  api.addNote(kind, title, content);
export const deleteNote = (id: string) => api.deleteNote(id);
