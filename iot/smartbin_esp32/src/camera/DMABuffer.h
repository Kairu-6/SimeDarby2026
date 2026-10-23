#pragma once

#include <new>
#include "esp_heap_caps.h"

class DMABuffer
{
  public:
  lldesc_t descriptor;
  unsigned char* buffer;
  bool valid;

  DMABuffer(int bytes)
    : buffer(nullptr), valid(false)
  {
    // Both the descriptor object and its data buffer must be in internal
    // DMA-capable RAM.  Plain malloc() normally works on a WROOM, but it
    // does not make this requirement explicit and becomes fragile as the
    // heap changes.
    buffer = (unsigned char *)heap_caps_malloc(
      bytes, MALLOC_CAP_DMA | MALLOC_CAP_8BIT
    );
    if (!buffer) return;

    descriptor.length = bytes;
    descriptor.size = descriptor.length;
    descriptor.owner = 1;
    descriptor.sosf = 1;
    descriptor.buf = (uint8_t*) buffer;
    descriptor.offset = 0;
    descriptor.empty = 0;
    descriptor.eof = 1;
    descriptor.qe.stqe_next = 0;
    valid = true;
  }

  static DMABuffer* create(int bytes)
  {
    void* storage = heap_caps_calloc(
      1, sizeof(DMABuffer), MALLOC_CAP_DMA | MALLOC_CAP_8BIT
    );
    if (!storage) return nullptr;

    DMABuffer* dma = new (storage) DMABuffer(bytes);
    if (!dma->valid) {
      dma->~DMABuffer();
      heap_caps_free(storage);
      return nullptr;
    }
    return dma;
  }

  void next(DMABuffer *next)
  {
    descriptor.qe.stqe_next = &(next->descriptor);
  }

  int sampleCount() const
  {
    return descriptor.length / 4;
  }

  ~DMABuffer()
  {
    if(buffer)
      heap_caps_free(buffer);
  }

  static void destroy(DMABuffer* dma)
  {
    if (!dma) return;
    dma->~DMABuffer();
    heap_caps_free(dma);
  }
};

