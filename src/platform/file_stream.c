#include "h1_sdk.h"
#include "diagnostics.h"
#include "loading.h"
#include "profile.h"
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <streams/file_stream.h>

struct RFILE { h1_file *handle; int64_t size, position; unsigned reads, seeks; };
void filestream_vfs_init(const struct retro_vfs_interface_info *info) { (void)info; }
RFILE *filestream_open(const char *path, unsigned mode, unsigned hints)
{
    h1_file *f;
    int size;
    RFILE *s;
    (void)hints;
    if (mode != RETRO_VFS_FILE_ACCESS_READ) return 0;
    h1_diag("ROM_FILE_OPEN_BEGIN mode=%u path=%s", mode, path);
    f = h1_fopen(path, "rb");
    h1_diag("ROM_FILE_OPEN_END handle=%p", f);
    if (!f) return 0;
    h1_diag("ROM_FILE_SIZE_BEGIN handle=%p", f);
    size = h1_fseek(f, 0, H1_SEEK_END);
    h1_diag("ROM_FILE_SIZE_END bytes=%d", size);
    if (size < 0) { h1_fclose(f); return 0; }
    h1_diag("ROM_FILE_REWIND_BEGIN");
    {
        int rc = h1_fseek(f, 0, H1_SEEK_SET);
        h1_diag("ROM_FILE_REWIND_END offset=%d", rc);
        if (rc != 0) { h1_fclose(f); return 0; }
    }
    s = (RFILE *)malloc(sizeof(*s));
    if (!s) { h1_fclose(f); return 0; }
    s->handle = f; s->size = size; s->position = 0; s->reads = s->seeks = 0;
    h1_loading_size((size_t)size < 2u*1024u*1024u ? (size_t)size : 2u*1024u*1024u);
    h1_diag("ROM_STREAM_READY stream=%p bytes=%d", s, size);
    return s;
}
int64_t filestream_get_size(RFILE *s) { return s ? s->size : -1; }
int64_t filestream_seek(RFILE *s, int64_t offset, int origin)
{
    int whence;
    int rc, trace;
    if (!s || offset < INT_MIN || offset > INT_MAX) return -1;
    if (origin == RETRO_VFS_SEEK_POSITION_START) whence = H1_SEEK_SET;
    else if (origin == RETRO_VFS_SEEK_POSITION_CURRENT) whence = H1_SEEK_CUR;
    else if (origin == RETRO_VFS_SEEK_POSITION_END) whence = H1_SEEK_END;
    else return -1;
    ++s->seeks; trace = h1_diag_is_verbose() && (s->seeks <= 16 || s->seeks % 128 == 0);
    if (trace) h1_diag("ROM_SEEK_BEGIN n=%u offset=%d origin=%d", s->seeks, (int)offset, whence);
    h1_profile_push(HP_ROM_IO);
    rc = h1_fseek(s->handle, (int)offset, whence);
    h1_profile_pop();
    if (trace || rc < 0) h1_diag("ROM_SEEK_END n=%u offset=%d", s->seeks, rc);
    if (rc >= 0) s->position = rc;
    return rc;
}
int64_t filestream_read(RFILE *s, void *buf, int64_t n)
{
    h1_size_t got;
    int trace;
    if (!s || n < 0 || n > INT_MAX) return -1;
    ++s->reads; trace = (h1_diag_is_verbose() && (s->reads <= 16 || s->reads % 128 == 0)) || (h1_loading_active() && n >= 1024 * 1024);
    if (trace) h1_diag("ROM_READ_BEGIN n=%u offset=%u requested=%u dst=%p", s->reads, (unsigned)s->position, (unsigned)n, buf);
    got = 0;
    do {
        h1_size_t requested = (h1_size_t)n-got;
        if (h1_loading_active() && requested > 65536u) requested = 65536u;
        h1_profile_push(HP_ROM_IO);
        h1_size_t chunk = h1_fread((uint8_t *)buf+got, 1, requested, s->handle);
        h1_profile_pop();
        if (chunk > requested) break;
        got += chunk;
        if (h1_loading_active()) h1_loading_read((size_t)s->position+got);
        if (chunk != requested) break;
    } while (got < (h1_size_t)n);
    if (trace || got != (h1_size_t)n) h1_diag("ROM_READ_END n=%u received=%u requested=%u", s->reads, got, (unsigned)n);
    if (got <= (h1_size_t)n) s->position += got;
    /* gpSP casts reads to u32: use zero on firmware read error. */
    return got <= (h1_size_t)n ? got : 0;
}
int filestream_close(RFILE *s)
{
    int rc;
    if (!s) return -1;
    h1_diag("ROM_FILE_CLOSE_BEGIN reads=%u seeks=%u", s->reads, s->seeks);
    rc = h1_fclose(s->handle);
    h1_diag("ROM_FILE_CLOSE_END rc=%d", rc);
    free(s); return rc;
}
