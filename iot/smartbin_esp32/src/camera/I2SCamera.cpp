//parts of his code are taken from
//https://github.com/igrr/esp32-cam-demo
//by Ivan Grokhotkov
//released under Apache License 2.0

#include "I2SCamera.h"
#include "Log.h"

volatile int I2SCamera::blocksReceived = 0;
volatile int I2SCamera::framesReceived = 0;
int I2SCamera::xres = 640;
int I2SCamera::yres = 480;
gpio_num_t I2SCamera::vSyncPin = (gpio_num_t)0;
intr_handle_t I2SCamera::i2sInterruptHandle = 0;
intr_handle_t I2SCamera::vSyncInterruptHandle = 0;
int I2SCamera::dmaBufferCount = 0;
volatile int I2SCamera::dmaBufferActive = 0;
DMABuffer **I2SCamera::dmaBuffer = 0;
unsigned char* I2SCamera::frame = 0;
unsigned char* I2SCamera::frameChunks[FRAME_CHUNK_COUNT] = {nullptr};
volatile int I2SCamera::framePointer = 0;
int I2SCamera::frameBytes = 0;
volatile bool I2SCamera::stopSignal = false;
volatile bool I2SCamera::frameReady = false;
volatile uint32_t I2SCamera::dmaErrors = 0;
volatile uint32_t I2SCamera::descriptorMismatches = 0;
volatile uint32_t I2SCamera::vsyncEdges = 0;
volatile int I2SCamera::rowsAtFirstVsync = -1;
volatile bool I2SCamera::captureActive = false;

void IRAM_ATTR I2SCamera::i2sInterrupt(void* arg)
{
    typeof(I2S0.int_st) status;
    status.val = I2S0.int_st.val;
    const uint32_t completedDescriptor = I2S0.in_eof_des_addr;
    I2S0.int_clr.val = status.val;
    if (!captureActive) return;
    if (status.in_dscr_err || status.rx_hung) {
      dmaErrors++;
      frameReady = false;
      i2sStop();
      stopSignal = false;
      return;
    }
    if (!status.in_suc_eof) return;
    // Hardware reports the completed descriptor. Do not silently copy a
    // different ring slot if interrupt delivery has fallen behind DMA.
    if (completedDescriptor != (uint32_t)&dmaBuffer[dmaBufferActive]->descriptor) {
      descriptorMismatches++;
      dmaErrors++;
      frameReady = false;
      i2sStop();
      stopSignal = false;
      return;
    }
    blocksReceived++;
    if (!dmaBuffer || dmaBufferCount <= 0 ||
        !dmaBuffer[dmaBufferActive] || !dmaBuffer[dmaBufferActive]->buffer) {
      dmaErrors++;
      return;
    }

    unsigned char* buf = dmaBuffer[dmaBufferActive]->buffer;
    dmaBufferActive = (dmaBufferActive + 1) % dmaBufferCount;
    const int row = blocksReceived - 1;
    if (row >= 0 && row < yres && framePointer < frameBytes)
    {
      unsigned char* dst;
      if(frameChunks[0])
      {
        const int chunkIndex = row / FRAME_ROWS_PER_CHUNK;
        const int rowWithinChunk = row % FRAME_ROWS_PER_CHUNK;
        if (chunkIndex >= FRAME_CHUNK_COUNT || !frameChunks[chunkIndex]) {
          dmaErrors++;
          return;
        }
        dst = frameChunks[chunkIndex] + rowWithinChunk * xres * 2;
      }
      else
      {
        dst = frame + framePointer;
      }
      for(int i = 0; i < xres * 4; i += 4)
      {
        *dst++ = buf[i + 2];
        *dst++ = buf[i];
      }
      framePointer += xres * 2;
    }
    else
    {
      dmaErrors++;
    }

    if (blocksReceived >= yres)
    {
      framesReceived++;
      frameReady = (dmaErrors == 0);
      if(stopSignal)
      {
        i2sStop();
        stopSignal = false;
      }
      else {
        framePointer = 0;
        blocksReceived = 0;
      }
    }
    //    i2sStop();
}

void IRAM_ATTR I2SCamera::vSyncInterrupt(void* arg)
{
    // Clear only the camera pin; other GPIO interrupt sources are not ours.
    if ((int)vSyncPin < 32) GPIO.status_w1tc = 1UL << (int)vSyncPin;
    else GPIO.status1_w1tc.val = 1UL << ((int)vSyncPin - 32);
    if(captureActive && gpio_get_level(vSyncPin))
    {
      if (vsyncEdges == 0) rowsAtFirstVsync = blocksReceived;
      vsyncEdges++;
    }
}

void IRAM_ATTR I2SCamera::i2sStop()
{
    captureActive = false;
    I2S0.conf.rx_start = 0;
    I2S0.int_ena.val = 0;
    I2S0.in_link.stop = 1;
}

void I2SCamera::i2sRun()
{
    DEBUG_PRINTLN("I2S Run");
    i2sStop();
    esp_intr_disable(i2sInterruptHandle);
    esp_intr_disable(vSyncInterruptHandle);
    i2sConfReset();
    blocksReceived = 0;
    dmaBufferActive = 0;
    framePointer = 0;
    frameReady = false;
    dmaErrors = 0;
    descriptorMismatches = 0;
    vsyncEdges = 0;
    rowsAtFirstVsync = -1;
    for (int i = 0; i < dmaBufferCount; i++) {
      dmaBuffer[i]->descriptor.length = xres * 4;
      dmaBuffer[i]->descriptor.owner = 1;
    }
    DEBUG_PRINT("Sample count ");
    DEBUG_PRINTLN(dmaBuffer[0]->sampleCount());
    I2S0.rx_eof_num = dmaBuffer[0]->sampleCount();
    I2S0.in_link.addr = (uint32_t)&(dmaBuffer[0]->descriptor);
    I2S0.int_clr.val = I2S0.int_raw.val;
    I2S0.int_ena.val = 0;
    I2S0.int_ena.in_suc_eof = 1;
    I2S0.int_ena.in_dscr_err = 1;
    I2S0.int_ena.rx_hung = 1;
    // Prepare first, then synchronize. Reset/setup after the falling edge
    // consumes the very timing margin needed to catch the first HREF.
    const unsigned long syncStart = micros();
    while (gpio_get_level(vSyncPin) == 0) {
      if (micros() - syncStart > 1000000UL) {
        dmaErrors++;
        i2sStop();
        return;
      }
    }
    while (gpio_get_level(vSyncPin) != 0) {
      if (micros() - syncStart > 1000000UL) {
        dmaErrors++;
        i2sStop();
        return;
      }
    }
    if ((int)vSyncPin < 32) GPIO.status_w1tc = 1UL << (int)vSyncPin;
    else GPIO.status1_w1tc.val = 1UL << ((int)vSyncPin - 32);
    captureActive = true;
    I2S0.in_link.start = 1;
    esp_intr_enable(i2sInterruptHandle);
    esp_intr_enable(vSyncInterruptHandle);
    I2S0.conf.rx_start = 1;
}

bool I2SCamera::initVSync(int pin)
{
  DEBUG_PRINT("Initializing VSYNC... ");
  vSyncPin = (gpio_num_t)pin;
  gpio_set_intr_type(vSyncPin, GPIO_INTR_POSEDGE);
  gpio_intr_enable(vSyncPin);
  if(gpio_isr_register(&vSyncInterrupt, (void*)"vSyncInterrupt", ESP_INTR_FLAG_INTRDISABLED | ESP_INTR_FLAG_IRAM, &vSyncInterruptHandle) != ESP_OK)
  {
    DEBUG_PRINTLN("failed!");
    return false;
  }
  DEBUG_PRINTLN("done.");
  return true;
}

void I2SCamera::deinitVSync()
{
  esp_intr_disable(vSyncInterruptHandle);
}

bool I2SCamera::init(const int XRES, const int YRES, const int VSYNC, const int HREF, const int XCLK, const int PCLK, const int D0, const int D1, const int D2, const int D3, const int D4, const int D5, const int D6, const int D7)
{
  xres = XRES;
  yres = YRES;
  frameBytes = XRES * YRES * 2;

  // NEW: the no-PSRAM ESP32 cannot allocate one 153600-byte QVGA frame.
  if (XRES == 320 && YRES == 240)
  {
    const int chunkBytes = 320 * 30 * 2;
    frame = nullptr;
    for (int i = 0; i < FRAME_CHUNK_COUNT; i++)
    {
      frameChunks[i] = (unsigned char*)malloc(chunkBytes);
      if (!frameChunks[i])
      {
        for (int j = 0; j < i; j++)
        {
          free(frameChunks[j]);
          frameChunks[j] = nullptr;
        }
        DEBUG_PRINTLN("Not enough memory for chunked frame buffer!");
        return false;
      }
    }
    // Compatibility pointer only; the upload code must use all chunks.
    frame = frameChunks[0];
  }
  else
  {
    frame = (unsigned char*)malloc(frameBytes);
    if(!frame)
    {
      DEBUG_PRINTLN("Not enough memory for frame buffer!");
      return false;
    }
  }

  if (!i2sInit(VSYNC, HREF, PCLK, D0, D1, D2, D3, D4, D5, D6, D7)) return false;
  if (!dmaBufferInit(xres * 2 * 2)) return false;
  if (!initVSync(VSYNC)) return false;
  return true;
}

bool I2SCamera::i2sInit(const int VSYNC, const int HREF, const int PCLK, const int D0, const int D1, const int D2, const int D3, const int D4, const int D5, const int D6, const int D7)
{
  int pins[] = {VSYNC, HREF, PCLK, D0, D1, D2, D3, D4, D5, D6, D7};
  gpio_config_t conf = {
    .pin_bit_mask = 0,
    .mode = GPIO_MODE_INPUT,
    .pull_up_en = GPIO_PULLUP_DISABLE,
    .pull_down_en = GPIO_PULLDOWN_DISABLE,
    .intr_type = GPIO_INTR_DISABLE
  };
    for (int i = 0; i < sizeof(pins) / sizeof(gpio_num_t); ++i) {
        conf.pin_bit_mask = 1LL << pins[i];
        gpio_config(&conf);
    }

    // Route input GPIOs to I2S peripheral using GPIO matrix, last parameter is invert
    gpio_matrix_in(D0,    I2S0I_DATA_IN0_IDX, false);
    gpio_matrix_in(D1,    I2S0I_DATA_IN1_IDX, false);
    gpio_matrix_in(D2,    I2S0I_DATA_IN2_IDX, false);
    gpio_matrix_in(D3,    I2S0I_DATA_IN3_IDX, false);
    gpio_matrix_in(D4,    I2S0I_DATA_IN4_IDX, false);
    gpio_matrix_in(D5,    I2S0I_DATA_IN5_IDX, false);
    gpio_matrix_in(D6,    I2S0I_DATA_IN6_IDX, false);
    gpio_matrix_in(D7,    I2S0I_DATA_IN7_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN8_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN9_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN10_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN11_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN12_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN13_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN14_IDX, false);
    gpio_matrix_in(0x30,  I2S0I_DATA_IN15_IDX, false);

    gpio_matrix_in(VSYNC, I2S0I_V_SYNC_IDX, true);
    gpio_matrix_in(0x38,  I2S0I_H_SYNC_IDX, false);  //0x30 sends 0, 0x38 sends 1
    gpio_matrix_in(HREF,  I2S0I_H_ENABLE_IDX, false);
    gpio_matrix_in(PCLK,  I2S0I_WS_IN_IDX, false);

    // Enable and configure I2S peripheral
    periph_module_enable(PERIPH_I2S0_MODULE);

    // Toggle some reset bits in LC_CONF register
    // Toggle some reset bits in CONF register
    i2sConfReset();
    // Enable slave mode (sampling clock is external)
    I2S0.conf.rx_slave_mod = 1;
    // Enable parallel mode
    I2S0.conf2.lcd_en = 1;
    // Use HSYNC/VSYNC/HREF to control sampling
    I2S0.conf2.camera_en = 1;
    // Configure clock divider
    I2S0.clkm_conf.clkm_div_a = 1;
    I2S0.clkm_conf.clkm_div_b = 0;
    I2S0.clkm_conf.clkm_div_num = 2;
    // FIFO will sink data to DMA
    I2S0.fifo_conf.dscr_en = 1;
    // FIFO configuration
    //two bytes per dword packing
    I2S0.fifo_conf.rx_fifo_mod = SM_0A0B_0C0D;  //pack two bytes in one dword see :https://github.com/igrr/esp32-cam-demo/issues/29
    I2S0.fifo_conf.rx_fifo_mod_force_en = 1;
    I2S0.conf_chan.rx_chan_mod = 1;
    // Clear flags which are used in I2S serial mode
    I2S0.sample_rate_conf.rx_bits_mod = 0;
    I2S0.conf.rx_right_first = 0;
    I2S0.conf.rx_msb_right = 0;
    I2S0.conf.rx_msb_shift = 0;
    I2S0.conf.rx_mono = 0;
    I2S0.conf.rx_short_sync = 0;
    I2S0.timing.val = 0;
    // Match Espressif's ESP32 camera receive synchronization setting.
    I2S0.timing.rx_dsync_sw = 1;

    // Allocate I2S interrupt, keep it disabled
    esp_intr_alloc(ETS_I2S0_INTR_SOURCE, ESP_INTR_FLAG_INTRDISABLED | ESP_INTR_FLAG_LEVEL1 | ESP_INTR_FLAG_IRAM, &i2sInterrupt, NULL, &i2sInterruptHandle);
    return true;
}

bool I2SCamera::dmaBufferInit(int bytes)
{
  dmaBufferCount = 8;
  dmaBuffer = (DMABuffer**)heap_caps_calloc(
    dmaBufferCount, sizeof(DMABuffer*), MALLOC_CAP_8BIT
  );
  if (!dmaBuffer) return false;

  for(int i = 0; i < dmaBufferCount; i++)
  {
    dmaBuffer[i] = DMABuffer::create(bytes);
    if (!dmaBuffer[i]) {
      for (int j = 0; j < i; j++) DMABuffer::destroy(dmaBuffer[j]);
      heap_caps_free(dmaBuffer);
      dmaBuffer = nullptr;
      dmaBufferCount = 0;
      return false;
    }
    if(i)
      dmaBuffer[i-1]->next(dmaBuffer[i]);
  }
  dmaBuffer[dmaBufferCount - 1]->next(dmaBuffer[0]);
  return true;
}

void I2SCamera::dmaBufferDeinit()
{
    if (!dmaBuffer) return;
    for(int i = 0; i < dmaBufferCount; i++)
      DMABuffer::destroy(dmaBuffer[i]);
    heap_caps_free(dmaBuffer);
    dmaBuffer = 0;
    dmaBufferCount = 0;
}
