#include "h1_sdk.h"
#include "diagnostics.h"
#include "jit.h"
#include "profile.h"
#include <stdint.h>
#include <stdlib.h>

static void *allocation, *cache;
static unsigned cache_size, sync_calls, sync_bytes;

void *map_jit_block(unsigned size)
{
    uintptr_t address;
    h1_diag("JIT_ALLOC_BEGIN bytes=%u", size);
    if (allocation || !size || size > 16u * 1024u * 1024u) return 0;
    allocation = malloc(size + 31u);
    address = ((uintptr_t)allocation + 31u) & ~31u;
    if (!allocation || address < 0x80000000u || address + size > 0x83c00000u) {
        free(allocation); allocation = 0;
        h1_diag("JIT_ALLOC_END ready=0 reason=memory"); return 0;
    }
    cache = (void *)address; cache_size = size;
    sync_calls = sync_bytes = 0;
    h1_diag("JIT_ALLOC_END ready=1 ptr=%p bytes=%u", cache, size);
    return cache;
}
void unmap_jit_block(void *address, unsigned size)
{
    if (address != cache || size != cache_size) return;
    h1_diag("JIT_FREE_BEGIN ptr=%p bytes=%u sync_calls=%u sync_bytes=%u",
            cache, size, sync_calls, sync_bytes);
    free(allocation); allocation = cache = 0; cache_size = 0;
    h1_diag("JIT_FREE_END");
}
int h1_jit_ready(void) { return cache != 0; }
void h1_jit_report(void)
{
    extern int dynarec_enable;
    h1_diag("JIT_STATE enabled=%d cache=%p bytes=%u", dynarec_enable, cache, cache_size);
}
/* Same MIPS32 cache operations used by the pinned SDK's H1 game loader.
 * Flush D first, then invalidate I, using 16-byte coverage for either line size.
 * H1 runs BDA code in KSEG0 with privileged CACHE instructions available. */
void h1_jit_cache_sync(void *start, void *end)
{
    uintptr_t address = (uintptr_t)start & ~15u;
    uintptr_t limit = ((uintptr_t)end + 15u) & ~15u;
    if (start >= end) return;
    h1_profile_push(HP_JIT);
    ++sync_calls; sync_bytes += (unsigned)((uintptr_t)end - (uintptr_t)start);
    __asm__ volatile("sync" ::: "memory");
    for (; address < limit; address += 16u)
        __asm__ volatile("cache 0x15, 0(%0)" :: "r"(address) : "memory");
    __asm__ volatile("sync" ::: "memory");
    for (address = (uintptr_t)start & ~15u; address < limit; address += 16u)
        __asm__ volatile("cache 0x10, 0(%0)" :: "r"(address) : "memory");
    __asm__ volatile("sync\n\tnop\n\tnop\n\tnop" ::: "memory");
    h1_profile_pop();
}
