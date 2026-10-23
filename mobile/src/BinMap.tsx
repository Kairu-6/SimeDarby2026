import React, { useState } from 'react';
import { Image, Linking, Pressable, View } from 'react-native';
import { Bin } from './types';
import { C, Icon, Text, s } from './ui';

// Web Mercator tiles are shared across native and web. No map API key required.
function project(lat: number, lon: number, zoom: number) {
  const size = 256 * 2 ** zoom;
  const sin = Math.sin((lat * Math.PI) / 180);
  return {
    x: ((lon + 180) / 360) * size,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * size,
  };
}
export default function BinMap({
  bins,
  selected,
  onSelect,
}: {
  bins: Bin[];
  selected?: string;
  onSelect: (bin: Bin) => void;
}) {
  const [national, setNational] = useState(false);
  const [size, setSize] = useState({ width: 600, height: 320 });
  const [zoomOffset, setZoomOffset] = useState(0);
  const [tileError, setTileError] = useState(false);
  const zoom = (national ? 5 : 10) + zoomOffset;
  const center = project(national ? 4.0 : 3.15, national ? 109.6 : 101.59, zoom);
  const left = center.x - size.width / 2,
    top = center.y - size.height / 2;
  const tiles = [];
  for (let x = Math.floor(left / 256); x <= Math.floor((left + size.width) / 256); x++) {
    for (let y = Math.floor(top / 256); y <= Math.floor((top + size.height) / 256); y++) {
      tiles.push(
        <Image
          key={`${zoom}-${x}-${y}`}
          source={{ uri: `https://tile.openstreetmap.org/${zoom}/${x}/${y}.png` }}
          onError={() => setTileError(true)}
          style={{
            position: 'absolute',
            left: x * 256 - left,
            top: y * 256 - top,
            width: 256,
            height: 256,
          }}
        />,
      );
    }
  }
  return (
    <View
      style={{ borderRadius: 12, overflow: 'hidden', backgroundColor: '#EAEDE4', height: 330 }}
      onLayout={(e) =>
        setSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height })
      }
    >
      {tiles}
      {bins.map((bin, index) => {
        const p = project(bin.latitude, bin.longitude, zoom);
        // Fan out colocated national markers so all seven stations remain selectable.
        const x = p.x - left + (national ? Math.cos(index * 2.4) * 19 : 0),
          y = p.y - top + (national ? Math.sin(index * 2.4) * 19 : 0);
        if (x < 0 || x > size.width || y < 0 || y > size.height) return null;
        const color =
          bin.status === 'full'
            ? C.red
            : bin.status === 'in_use'
              ? C.orange
              : bin.status === 'offline'
                ? C.muted
                : C.green;
        return (
          <Pressable
            key={bin.id}
            accessibilityRole="button"
            accessibilityLabel={`${bin.name}: ${bin.status.replace('_', ' ')}`}
            onPress={() => onSelect(bin)}
            style={{
              position: 'absolute',
              left: x - 19,
              top: y - 20,
              width: 40,
              height: 40,
              borderRadius: 22,
              backgroundColor: color,
              borderWidth: selected === bin.id ? 4 : 3,
              borderColor: selected === bin.id ? '#FFC6A8' : 'white',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 3px 10px #00000026',
              zIndex: selected === bin.id ? 3 : 2,
            }}
          >
            <Icon name="leaf" color="white" size={17} />
          </Pressable>
        );
      })}
      <View
        style={{
          position: 'absolute',
          left: 12,
          top: 12,
          flexDirection: 'row',
          backgroundColor: 'white',
          borderRadius: 8,
          padding: 3,
          boxShadow: '0 2px 8px #00000010',
        }}
      >
        {['Nearby', 'Malaysia'].map((label, i) => (
          <Pressable
            key={label}
            accessibilityRole="button"
            onPress={() => {
              setNational(i === 1);
              setZoomOffset(0);
            }}
            style={{
              paddingVertical: 10,
              paddingHorizontal: 13,
              backgroundColor: national === (i === 1) ? C.ink : 'white',
              borderRadius: 6,
            }}
          >
            <Text
              style={{
                color: national === (i === 1) ? 'white' : C.body,
                fontSize: 11,
                fontWeight: '600',
              }}
            >
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
      <View
        style={{
          position: 'absolute',
          right: 12,
          bottom: 35,
          backgroundColor: 'white',
          borderRadius: 8,
        }}
      >
        {[1, -1].map((change) => (
          <Pressable
            key={change}
            accessibilityRole="button"
            accessibilityLabel={change === 1 ? 'Zoom in' : 'Zoom out'}
            onPress={() => setZoomOffset((v) => Math.max(-2, Math.min(3, v + change)))}
            style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}
          >
            <Icon name={change === 1 ? 'add' : 'remove'} />
          </Pressable>
        ))}
      </View>
      {tileError && (
        <View
          style={{
            position: 'absolute',
            bottom: 26,
            left: 12,
            backgroundColor: 'white',
            padding: 7,
            borderRadius: 5,
          }}
        >
          <Text style={s.caption}>Map tiles unavailable. Stations still appear by location.</Text>
        </View>
      )}
      <Pressable
        accessibilityRole="link"
        onPress={() => Linking.openURL('https://www.openstreetmap.org/copyright')}
        style={{
          position: 'absolute',
          bottom: 0,
          right: 0,
          backgroundColor: '#FFFFFFEB',
          padding: 5,
        }}
      >
        <Text style={{ fontSize: 9, color: C.body }}>© OpenStreetMap contributors</Text>
      </Pressable>
    </View>
  );
}
