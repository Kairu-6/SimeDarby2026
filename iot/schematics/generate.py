"""Rebuild the editable SVG wiring sheets using only Python's standard library."""
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent


class Sheet:
    def __init__(self, title, subtitle, height=1000):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" viewBox="0 0 1400 {height}">', '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0L9 4.5L0 9" fill="#305d80"/></marker></defs>', f'<rect width="1400" height="{height}" fill="#fff"/>']
        self.text(40,45,title,28,"#222",True)
        self.text(40,76,subtitle,16,"#5c6067")

    def text(self,x,y,label,size=16,color="#222",bold=False):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}">{escape(label)}</text>')

    def box(self,x,y,w,h,title,lines,color="#edf4f8"):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{color}" stroke="#9aa4ad"/>')
        self.text(x+18,y+32,title,19,bold=True)
        for i,line in enumerate(lines): self.text(x+18,y+61+i*23,line,15)

    def wire(self,points,color="#305d80",arrow=False):
        self.parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"'+(' marker-end="url(#arrow)"' if arrow else '')+'/>')

    def save(self,name):
        (ROOT/name).write_text("\n".join(self.parts+["</svg>"]),encoding="utf-8")


def overview():
    s=Sheet("Sime Loop: current SmartBin wiring", "Matches the supplied firmware and Desktop/Arduino camera project. Bin 1=recyclable; bin 2=food; bin 3=reject.")
    s.box(35,125,315,350,"OV7670 parallel module",[
        "Camera signal -> ESP32 GPIO",
        "D0 5      D1 18     D2 19     D3 21",
        "D4 33     D5 32     D6 34     D7 35",
        "XCLK 4     PCLK 22",
        "VSYNC 25   HREF 23",
        "SIOD/SDA 26   SIOC/SCL 27",
        "VCC -> 3V3; GND -> GND",
        "RESET -> 3V3; PWDN -> GND",
        "Short wires; check module pull-ups",
        "QVGA 320 x 240 RGB565"
    ],"#eaf4ed")
    s.box(435,125,300,350,"ESP32 NodeMCU-32S",[
        "Wi-Fi / camera / weight / API",
        "UART2 TX: GPIO17",
        "UART2 RX: GPIO16 (3.3 V)",
        "HX711 DOUT: GPIO36 / VP",
        "HX711 SCK: GPIO13",
        "Camera uses remaining mapped IO",
        "ESP32 logic powered via USB",
        "GPIO labels, not header numbers",
        "No servo power from this board"
    ])
    s.box(850,125,250,350,"Nano V3 / ATmega328P",[
        "UART RX: D12 / TX: A0",
        "Food SG90: D9 (bin 2)",
        "Recycle SG90: D8 (bin 1)",
        "Reject SG90: D10 (bin 3)",
        "Pusher MG996R: D11",
        "3 ultrasound pairs at right",
        "9600 baud, 8N1, JSON lines",
        "SoftwareSerial on D12 / A0",
        "USB logic / external servo power"
    ],"#fff0e6")
    s.wire("350,290 435,290","#28794c");s.text(354,276,"Camera bus",12)
    s.wire("735,265 850,265");s.text(742,248,"UART TX/RX",13)
    s.text(742,288,"See divider sheet",12)
    for y,title,lines in [
        (125,"Food HC-SR04",["TRIG -> D4; ECHO -> D5","VCC -> Nano 5V","GND -> common ground"]),
        (275,"Recycle HC-SR04",["TRIG -> D2; ECHO -> D3","VCC -> Nano 5V","GND -> common ground"]),
        (425,"Reject HC-SR04",["TRIG -> D6; ECHO -> D7","VCC -> Nano 5V","GND -> common ground"]),
    ]:
        s.box(1140,y,225,130,title,lines,"#f5f3e8")
        anchor=y+65
        s.wire(f"1100,{min(anchor,450)} 1120,{min(anchor,450)} 1120,{anchor} 1140,{anchor}","#8d7628")
    s.box(35,535,315,200,"HX711 amplifier module",[
        "VCC/VDD logic -> ESP32 3V3",
        "GND -> common ground",
        "DT / DOUT -> GPIO36",
        "SCK / CLK -> GPIO13",
        "E+ E- A+ A- -> 5 kg load cell",
        "Single-VCC module: use 3.3 V"
    ],"#eaf4ed")
    s.wire("350,620 390,620 390,405 435,405","#28794c")
    s.box(35,795,315,120,"5 kg load cell + plate",["One end fixed; plate on moving end","Verify wire labels; tare empty plate"],"#f3f3f3")
    s.wire("195,795 195,735","#28794c")
    s.box(435,535,300,200,"Computer / backend",[
        "Python FastAPI + local CLIP",
        "POST /telemetry",
        "QR claim -> check -> sort receipt",
        "Food / recyclable / reject / hold",
        "Frozen item weight -> points",
        "Reject receives zero points"
    ])
    s.wire("585,475 585,535",arrow=True);s.text(600,510,"Wi-Fi / HTTP",14)
    s.box(850,620,515,130,"Three SG90 180-degree door servos",[
        "Food D9; recyclable D8; reject D10",
        "Servo V+ -> external regulated 5 V; GND -> common",
        "Only the selected door opens; others commanded closed"
    ],"#fff0e6")
    s.wire("965,475 965,620","#d9752b");s.text(980,580,"3 signal wires",14)
    s.box(850,795,515,120,"MG996R 360-degree continuous pusher",[
        "Signal D11; V+ external 5 V; GND common",
        "Neutral/start pulses; stop when HX711 plate is empty"
    ],"#fff0e6")
    s.wire("1080,475 1110,590 1380,590 1380,850 1365,850","#d9752b")
    s.text(40,960,"Logic and servo positive rails stay separate; all grounds join. No end-stop or physical door-position feedback is present.",16,"#a52c22")
    s.save("wiring-overview.svg")


def power():
    s=Sheet("UART level divider and power distribution", "Nano is 5 V logic; ESP32 GPIO is 3.3 V. The invoice's 1k and 2k resistors form the Nano-TX divider.")
    s.text(70,165,"Nano A0 / TX (5 V)",20,bold=True)
    s.text(1010,165,"ESP32 GPIO16 / RX",20,bold=True)
    s.wire("90,205 340,205")
    s.parts.append('<rect x="340" y="190" width="110" height="30" fill="#fff" stroke="#222" stroke-width="2"/>')
    s.text(350,180,"R1 = 1k",16)
    s.wire("450,205 680,205 1260,205")
    s.parts.append('<circle cx="680" cy="205" r="6" fill="#305d80"/>')
    s.wire("680,205 680,275")
    s.parts.append('<rect x="665" y="275" width="30" height="100" fill="#fff" stroke="#222" stroke-width="2"/>')
    s.text(715,330,"R2 = 2k",18)
    s.wire("680,375 680,425","#222")
    s.wire("650,425 710,425","#222");s.wire("660,436 700,436","#222");s.wire("670,447 690,447","#222")
    s.text(715,425,"Common GND",16)
    s.text(770,275,"Node nominal voltage: 5 x 2 / (1 + 2) = 3.33 V",17)
    s.text(770,310,"Do not connect Nano TX directly to ESP32 RX.",17,"#a52c22",True)
    s.text(70,495,"ESP32 GPIO17 / TX (3.3 V)",20,bold=True)
    s.text(1010,495,"Nano D12 / RX",20,bold=True)
    s.wire("90,530 1260,530","#28794c",True)
    s.text(370,562,"Direct 3.3 V signal to the classic 5 V ATmega328P RX input",16)
    s.box(45,615,610,180,"Logic supply",[
        "ESP32 USB -> onboard 3V3 -> OV7670 module and HX711",
        "Nano USB / regulated 5 V logic -> HC-SR04 VCC pins",
        "D0/D1 remain free for Nano USB serial debugging",
        "Servo current must bypass Nano regulators and breadboard rails",
        "Never join independent USB and external positive supplies blindly"
    ])
    s.box(735,615,610,180,"Servo supply: separate high-current 5 V rail",[
        "Regulated 5 V supply sized for all four servo peak currents",
        "Bench design target: 5 A; confirm the actual servo specifications",
        "All servo V+ wires -> this supply; not board 5V/3V3 outputs",
        "Bulk decoupling near servo rail; short adequate-gauge power leads",
        "4xAA holder is not a regulated servo supply"
    ],"#fff0e6")
    s.wire("90,875 1310,875","#222")
    for x,label in [(100,"ESP32 GND"),(340,"Nano GND"),(580,"HX711/camera GND"),(860,"HC-SR04 GND"),(1160,"Servo supply GND")]:
        s.wire(f"{x},840 {x},875","#222");s.text(x-45,825,label,14)
    s.text(450,920,"Common ground is the UART, sensor and servo signal reference.",19,bold=True)
    s.text(45,966,"Hardware reference only. Confirm module variants, camera byte order, servo travel/neutral and power ratings on the bench.",15,"#a52c22")
    s.save("uart-and-power.svg")


if __name__=="__main__":
    overview();power()
