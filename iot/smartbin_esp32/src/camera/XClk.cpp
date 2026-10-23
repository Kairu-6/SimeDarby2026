// Fixed XClk.cpp for arduino-esp32 v2.0.17
// Original by bitluni: https://github.com/bitluni/ESP32CameraI2S
//
// Changes from original:
//   1. bit_num -> duty_resolution  (field renamed in ESP-IDF v4+)
//   2. Added clk_cfg = LEDC_AUTO_CLK  (new required field)
//
// Without these fixes you get:
//   assert failed: ledc_clk_cfg_to_global_clk ledc.c:444

#include "XClk.h"
#include "driver/ledc.h"

bool ClockEnable(int pin, int Hz)
{
    periph_module_enable(PERIPH_LEDC_MODULE);

    ledc_timer_config_t timer_conf;
    timer_conf.duty_resolution = LEDC_TIMER_1_BIT;  // FIX: was "bit_num"
    timer_conf.freq_hz = Hz;
    timer_conf.speed_mode = LEDC_HIGH_SPEED_MODE;
    timer_conf.timer_num = LEDC_TIMER_0;
    timer_conf.clk_cfg = LEDC_AUTO_CLK;              // FIX: was missing
    esp_err_t err = ledc_timer_config(&timer_conf);
    if (err != ESP_OK) {
        return false;
    }

    ledc_channel_config_t ch_conf;
    ch_conf.channel = LEDC_CHANNEL_0;
    ch_conf.timer_sel = LEDC_TIMER_0;
    ch_conf.intr_type = LEDC_INTR_DISABLE;
    ch_conf.duty = 1;
    ch_conf.speed_mode = LEDC_HIGH_SPEED_MODE;
    ch_conf.gpio_num = pin;
    ch_conf.hpoint = 0;
    err = ledc_channel_config(&ch_conf);
    if (err != ESP_OK) {
        return false;
    }
    return true;
}

void ClockDisable()
{
    periph_module_disable(PERIPH_LEDC_MODULE);
}
