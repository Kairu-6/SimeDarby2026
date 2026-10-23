import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text as NativeText,
  View,
  ViewStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Ellipse, Path, Rect, G } from 'react-native-svg';

export const C = {
  red: '#D71920',
  darkRed: '#A90F17',
  ink: '#292929',
  body: '#404040',
  muted: '#6B7280',
  bg: '#F5F5F5',
  border: '#E5E5E5',
  white: '#FFFFFF',
  peach: '#FFF0E6',
  yellow: '#FFF5D6',
  orange: '#F36F21',
  green: '#28794C',
  greenBg: '#EAF4EC',
};
export function Text({ style, ...props }: React.ComponentProps<typeof NativeText>) {
  const weight = String(StyleSheet.flatten(style)?.fontWeight || '400');
  const font =
    weight === '800'
      ? 'DMSans_800ExtraBold'
      : ['700', 'bold'].includes(weight)
        ? 'DMSans_700Bold'
        : weight === '600'
          ? 'DMSans_600SemiBold'
          : weight === '500'
            ? 'DMSans_500Medium'
            : 'DMSans_400Regular';
  return <NativeText {...props} style={[style, { fontFamily: font, fontWeight: 'normal' }]} />;
}
export type IconName = React.ComponentProps<typeof Ionicons>['name'];
export const Icon = ({
  name,
  color = C.muted,
  size = 20,
}: {
  name: IconName;
  color?: string;
  size?: number;
}) => <Ionicons name={name} size={size} color={color} />;
export const fmt = (n: number) => n.toLocaleString('en-MY');
export const initials = (name: string) =>
  name
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('');
export function Button({
  title,
  onPress,
  secondary,
  small,
  disabled,
  loading,
  icon,
  style,
}: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  small?: boolean;
  disabled?: boolean;
  loading?: boolean;
  icon?: IconName;
  style?: ViewStyle;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        secondary && s.secondary,
        small && { minHeight: 42, paddingHorizontal: 16 },
        (disabled || loading) && { opacity: 0.45 },
        pressed && { opacity: 0.8, transform: [{ scale: 0.99 }] },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={secondary ? C.red : C.white} size="small" />
      ) : icon ? (
        <Icon name={icon} size={18} color={secondary ? C.red : C.white} />
      ) : null}
      <Text style={[s.buttonText, secondary && { color: C.red }]}>{title}</Text>
    </Pressable>
  );
}
export function Avatar({
  name,
  size = 42,
  color = '#F8E5DF',
}: {
  name: string;
  size?: number;
  color?: string;
}) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <Text style={{ fontWeight: '700', fontSize: size * 0.32, color: C.darkRed }}>
        {initials(name)}
      </Text>
    </View>
  );
}
export function Badge({
  label,
  color = C.green,
  bg = C.greenBg,
}: {
  label: string;
  color?: string;
  bg?: string;
}) {
  return (
    <View style={[s.badge, { backgroundColor: bg }]}>
      <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: color }} />
      <Text style={{ color, fontSize: 11, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}
export function SectionTitle({
  title,
  action,
  onPress,
}: {
  title: string;
  action?: string;
  onPress?: () => void;
}) {
  return (
    <View style={s.sectionTitle}>
      <Text style={[s.h2, { flexShrink: 1 }]}>{title}</Text>
      {action && (
        <Pressable
          accessibilityRole="button"
          onPress={onPress}
          style={{ minHeight: 44, justifyContent: 'center' }}
        >
          <Text style={{ fontSize: 12, fontWeight: '600', color: C.red }}>
            {action} <Ionicons name="arrow-forward" />
          </Text>
        </Pressable>
      )}
    </View>
  );
}
export function Empty({
  icon = 'leaf-outline',
  title,
  text,
}: {
  icon?: IconName;
  title: string;
  text: string;
}) {
  return (
    <View style={{ alignItems: 'center', padding: 35, gap: 10 }}>
      <Icon name={icon} size={32} color={C.red} />
      <Text style={s.h3}>{title}</Text>
      <Text style={[s.body, { textAlign: 'center', maxWidth: 320 }]}>{text}</Text>
    </View>
  );
}
export function FillBar({ value, label }: { value: number; label: string }) {
  const color = value >= 90 ? C.red : C.green;
  return (
    <View style={{ flex: 1, gap: 7 }}>
      <View style={s.between}>
        <Text style={s.caption}>{label}</Text>
        <Text style={[s.caption, { color, fontWeight: '700' }]}>{Math.round(value)}%</Text>
      </View>
      <View style={{ height: 5, backgroundColor: '#ECEEEA', borderRadius: 4, overflow: 'hidden' }}>
        <View style={{ width: `${value}%`, height: 5, backgroundColor: color, borderRadius: 4 }} />
      </View>
    </View>
  );
}
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
      <View
        style={{
          backgroundColor: C.red,
          borderRadius: 13,
          width: 39,
          height: 39,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon name="infinite" size={28} color="white" />
      </View>
      <View>
        <Text
          style={{
            fontSize: compact ? 19 : 23,
            color: C.ink,
            fontWeight: '800',
            letterSpacing: -0.8,
          }}
        >
          sime<Text style={{ color: C.red }}>loop</Text>
          <Text style={{ color: C.red, fontSize: 23 }}>.</Text>
        </Text>
        {!compact && (
          <Text style={{ color: C.muted, fontSize: 9, letterSpacing: 1.1, marginTop: 1 }}>
            A GREENER EVERYDAY
          </Text>
        )}
      </View>
    </View>
  );
}

export function EcoArt({ width = 260 }: { width?: number }) {
  return (
    <Svg
      width={width}
      height={width * 0.85}
      viewBox="0 0 320 270"
      accessibilityLabel="Recycling and food waste bins with growing leaves"
    >
      <Circle cx="170" cy="135" r="109" fill="#F7DFCC" />
      <Circle cx="266" cy="60" r="16" fill="#FFF5D6" />
      <Circle cx="52" cy="155" r="7" fill="#EDC6AD" />
      <Ellipse cx="173" cy="239" rx="122" ry="12" fill="#E9D2BF" />
      <Path d="M243 218 Q230 150 267 97" fill="none" stroke="#528456" strokeWidth="4" />
      <Path
        d="M253 140 Q220 143 220 114 Q248 112 253 140M263 115 Q291 114 286 85 Q258 88 263 115M245 171 Q271 174 277 147 Q248 144 245 171"
        fill="#6E996C"
      />
      <G rotation="-8" origin="125,170">
        <Rect x="62" y="114" width="108" height="117" rx="15" fill="#387D62" />
        <Rect x="56" y="107" width="120" height="21" rx="7" fill="#235D48" />
        <Rect x="88" y="96" width="55" height="11" rx="5" fill="#235D48" />
        <Path
          d="M111 150 L126 174 H117 L122 187 M137 186 L111 187 L116 180 M101 178 L89 157 L98 157 L105 145"
          fill="none"
          stroke="#C9E3C8"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <Circle cx="82" cy="233" r="7" fill="#292929" />
        <Circle cx="152" cy="233" r="7" fill="#292929" />
      </G>
      <G rotation="8" origin="213,185">
        <Rect x="164" y="139" width="93" height="94" rx="13" fill="#D95C41" />
        <Rect x="158" y="131" width="105" height="19" rx="6" fill="#B54331" />
        <Rect x="187" y="121" width="45" height="10" rx="4" fill="#B54331" />
        <Path
          d="M210 170 C185 175 188 197 210 201 C233 198 235 175 210 170 M211 171 Q206 163 211 160 M211 169 Q223 157 228 166 Q221 174 211 169"
          fill="#FFE4C8"
        />
        <Circle cx="181" cy="235" r="6" fill="#292929" />
        <Circle cx="240" cy="235" r="6" fill="#292929" />
      </G>
      <G rotation="20" origin="120,69">
        <Rect
          x="109"
          y="42"
          width="23"
          height="48"
          rx="7"
          fill="#F8FCF7"
          stroke="#88A89B"
          strokeWidth="2"
        />
        <Rect
          x="114"
          y="32"
          width="13"
          height="14"
          rx="3"
          fill="#D7E6DC"
          stroke="#88A89B"
          strokeWidth="2"
        />
        <Rect x="109" y="59" width="23" height="16" fill="#B5D4BC" />
      </G>
      <Path d="M183 59 Q167 34 190 25 Q211 47 183 59" fill="#74A070" />
      <Path d="M173 79 L190 37" stroke="#477550" strokeWidth="2" fill="none" />
      <Path
        d="M69 64 v10 M64 69 h10 M285 193 v12 M279 199 h12"
        stroke="#C28A5B"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </Svg>
  );
}

export const s = StyleSheet.create({
  page: { gap: 24, paddingBottom: 28 },
  card: {
    backgroundColor: C.white,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: C.border,
    padding: 24,
  },
  h1: { fontSize: 30, fontWeight: '700', letterSpacing: -0.9, color: C.ink },
  h2: { fontSize: 18, fontWeight: '700', letterSpacing: -0.4, color: C.ink },
  h3: { fontSize: 15, fontWeight: '600', color: C.ink },
  body: { fontSize: 13, lineHeight: 21, color: C.muted },
  caption: { fontSize: 11, lineHeight: 17, color: C.muted },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  between: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  button: {
    minHeight: 48,
    paddingHorizontal: 21,
    paddingVertical: 12,
    borderRadius: 10,
    backgroundColor: C.red,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  buttonText: { fontSize: 13, fontWeight: '600', color: 'white' },
  secondary: { backgroundColor: 'white', borderWidth: 1, borderColor: C.red },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'flex-start',
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 20,
  },
  sectionTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 30,
    marginBottom: 16,
  },
  input: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    color: C.ink,
    backgroundColor: 'white',
  },
  divider: { height: 1, backgroundColor: C.border },
});
