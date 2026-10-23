import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import QRCode from 'react-native-qrcode-svg';
import Svg, { Circle, Ellipse, Path, Rect } from 'react-native-svg';
import { DEFAULT_API, request, requestId } from './api';
import { Brand, Button, C, Icon, Text, s } from './ui';
import type { Deposit, User } from './types';

type Category = 'food' | 'recyclable';
type Station = {
  id: string;
  name: string;
  township: string;
  online: boolean;
  busy: boolean;
  demo_mode: boolean;
  app_url: string;
  pairing_required: boolean;
  points_per_kg: Record<Category, number>;
  compartments: Record<Category | 'reject', { fill_percent: number; full: boolean }>;
  leaderboard: { name: string; rank: number; points: number }[];
};
type Offer = {
  id: string;
  bin_id: string;
  category: Category;
  expires_at: string;
  state: string;
  claim_key?: string;
  claim_url?: string;
  resident_first_name?: string;
  deposit: Deposit | null;
};
const LABEL = { food: 'Food waste', recyclable: 'Recyclables' };
const STORE = 'simeloop-kiosk-v3';

function MaterialArt({ category, size = 160 }: { category: Category; size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 180 180" accessibilityLabel={LABEL[category]}>
      <Ellipse cx="90" cy="157" rx="62" ry="8" fill={category === 'food' ? '#EAC7AF' : '#BDD3C0'} />
      {category === 'recyclable' ? (
        <>
          <Path
            d="M48 25H70V46L81 63V141Q81 150 72 150H46Q37 150 37 141V63L48 46Z"
            fill="#A6C8AE"
            stroke="#285F40"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <Rect x="46" y="17" width="26" height="14" rx="4" fill="#285F40" />
          <Rect x="39" y="78" width="40" height="38" fill="#F7FCF6" />
          <Path
            d="M54 90L62 90L67 100M67 95L67 101L61 100M64 105L54 108L49 99"
            stroke="#285F40"
            strokeWidth="3"
            fill="none"
            strokeLinecap="round"
          />
          <Rect
            x="101"
            y="72"
            width="44"
            height="78"
            rx="11"
            fill="#E6EBD5"
            stroke="#586D45"
            strokeWidth="3"
          />
          <Ellipse
            cx="123"
            cy="75"
            rx="22"
            ry="8"
            fill="#F9FBEF"
            stroke="#586D45"
            strokeWidth="3"
          />
          <Path
            d="M118 73H128M106 91H140M106 133H140"
            stroke="#586D45"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </>
      ) : (
        <>
          <Path
            d="M41 95Q85 67 139 90Q134 143 92 149Q48 145 41 95Z"
            fill="#E8A470"
            stroke="#8C4E29"
            strokeWidth="3"
          />
          <Ellipse
            cx="90"
            cy="94"
            rx="50"
            ry="14"
            fill="#FFF6E3"
            stroke="#8C4E29"
            strokeWidth="3"
          />
          <Path
            d="M66 91Q49 62 63 42Q70 29 84 35Q96 47 87 66Q81 78 84 93"
            fill="#F6CC63"
            stroke="#956122"
            strokeWidth="3"
          />
          <Path
            d="M66 80Q68 57 78 46M62 40L56 32"
            fill="none"
            stroke="#956122"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <Path
            d="M97 89Q94 56 124 50Q138 72 109 91Z"
            fill="#7FA66C"
            stroke="#42633A"
            strokeWidth="3"
          />
          <Path d="M104 84L123 58" fill="none" stroke="#42633A" strokeWidth="3" />
          <Circle cx="97" cy="96" r="10" fill="#E78B4B" />
        </>
      )}
    </Svg>
  );
}

export default function Kiosk() {
  const { width } = useWindowDimensions();
  const wide = width >= 850;
  const [base, setBase] = useState(DEFAULT_API);
  const [stationId, setStationId] = useState('ELM-01');
  const [pairingKey, setPairingKey] = useState('');
  const [station, setStation] = useState<Station | null>(null);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(false);
  const [demo, setDemo] = useState(false);
  const [ready, setReady] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const lock = useRef(false);
  const demoToken = useRef<string | null>(null);
  const completionId = useRef(requestId());
  const headers = (): Record<string, string> => (pairingKey ? { 'X-Kiosk-Key': pairingKey } : {});

  async function kioskRequest<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(base.replace(/\/$/, '') + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {
        ...headers(),
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : 'The station could not complete that request. Try again.',
      );
    return data;
  }
  async function refresh() {
    const next = await kioskRequest<Station>(
      `/api/kiosk/stations/${encodeURIComponent(stationId)}`,
    );
    setStation(next);
    if (offer) {
      const update = await kioskRequest<Offer>(`/api/kiosk/offers/${offer.id}`);
      setOffer((previous) => (previous ? { ...previous, ...update } : null));
    }
  }
  async function act(work: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection lost. Please try again.');
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  useEffect(() => {
    AsyncStorage.getItem(STORE)
      .then((saved) => {
        if (saved) {
          const v = JSON.parse(saved);
          setBase(v.base || DEFAULT_API);
          setStationId(v.stationId || 'ELM-01');
          setPairingKey(v.pairingKey || '');
          setOffer(v.offer || null);
        }
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (!ready || settings) return;
    let active = true;
    const update = () =>
      refresh().catch(() => {
        if (active)
          setError(
            'The station service is unavailable. Please retry or check Connection settings.',
          );
      });
    void update();
    const timer = setInterval(update, offer ? 2000 : 8000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [ready, base, stationId, pairingKey, offer?.id, settings]);
  useEffect(() => {
    if (ready)
      void AsyncStorage.setItem(STORE, JSON.stringify({ base, stationId, pairingKey, offer }));
  }, [ready, base, stationId, pairingKey, offer]);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  function reset() {
    setOffer(null);
    setDemo(false);
    setError('');
    completionId.current = requestId();
  }
  function choose(category: Category) {
    void act(async () => {
      const next = await kioskRequest<Offer>(
        `/api/kiosk/stations/${encodeURIComponent(stationId)}/offers`,
        { category },
      );
    if (process.env.EXPO_PUBLIC_APP_URL && next.claim_key) next.claim_url = process.env.EXPO_PUBLIC_APP_URL.replace(/\/$/, '') + '/?claim=' + next.claim_key;
    setOffer(next);
      completionId.current = requestId();
    });
  }
  async function getDemoToken() {
    if (!demoToken.current)
      demoToken.current = (
        await request<{ token: string; user: User }>(base, '/api/auth/login', null, {
          email: 'resident@simeloop.demo',
          password: 'Loop123!',
        })
      ).token;
    return demoToken.current;
  }
  function demoAction(action: 'connect' | 'match' | 'mismatch' | 'complete') {
    void act(async () => {
      if (!offer) return;
      const token = await getDemoToken();
      if (action === 'connect')
        await request(base, '/api/kiosk/claim', token, { key: offer.claim_key });
      else if (offer.deposit) {
        if (action === 'complete')
          await request(base, `/api/demo/deposits/${offer.deposit.id}/confirm`, token, {
            weight_kg: 0.5,
            event_id: completionId.current,
          });
        else
          await request(base, `/api/demo/deposits/${offer.deposit.id}/classify`, token, {
            category:
              action === 'match'
                ? offer.category
                : offer.category === 'food'
                  ? 'recyclable'
                  : 'food',
          });
      }
      await refresh();
    });
  }

  const seconds = offer
    ? Math.max(0, Math.ceil((new Date(offer.expires_at).getTime() - clock) / 1000))
    : 0;
  const expired = offer?.state === 'expired' || (offer?.state === 'waiting' && seconds === 0);
  const terminal = !!offer && (expired || ['cancelled', 'completed'].includes(offer.state));
  const selected = offer?.category || 'recyclable';
  const checking = offer?.state === 'checking';
  const verified = offer?.state === 'sorting';
  const alert = offer?.deposit?.verification_message && !verified && offer.state === 'claimed';
  const time = new Date(clock).toLocaleTimeString('en-MY', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, padding: wide ? 24 : 20 }}>
        <View
          style={{
            width: '100%',
            maxWidth: 1380,
            alignSelf: 'center',
            gap: 22,
            flex: 1,
          }}
        >
          <View style={[s.between, { gap: 16, flexWrap: 'wrap' }]}>
            <Brand />
            <View style={[s.row, { gap: 14 }]}>
              <View style={{ alignItems: 'flex-end', gap: 3 }}>
                <Text style={s.h3}>{station?.name || 'Elmina Lakeside'}</Text>
                <Text style={s.caption}>
                  {station?.township || 'City of Elmina'} · {time}
                </Text>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Connection settings"
                onPress={() => setSettings(!settings)}
                style={ks.settings}
              >
                <Icon name="settings-outline" color={C.ink} />
              </Pressable>
            </View>
          </View>

          {settings ? (
            <View style={[ks.panel, { maxWidth: 650, gap: 16 }]}>
              <Text style={s.h1}>Station settings</Text>
              <Text style={s.body}>
                Pair this screen with your station. The kiosk key is different from the ESP32 device
                key.
              </Text>
              <Text style={s.h3}>API address</Text>
              <TextInput
                accessibilityLabel="API address"
                value={base}
                onChangeText={setBase}
                style={s.input}
                autoCapitalize="none"
              />
              <Text style={s.h3}>Station ID</Text>
              <TextInput
                accessibilityLabel="Station ID"
                value={stationId}
                onChangeText={setStationId}
                style={s.input}
                autoCapitalize="none"
              />
              <Text style={s.h3}>Kiosk pairing key</Text>
              <TextInput
                accessibilityLabel="Kiosk pairing key"
                value={pairingKey}
                onChangeText={setPairingKey}
                style={s.input}
                secureTextEntry
                autoCapitalize="none"
              />
              <Button
                title="Save & connect"
                onPress={() => {
                  setError('');
                  setStation(null);
                  setSettings(false);
                  reset();
                }}
              />
            </View>
          ) : (
            <>
              {error ? (
                <View accessibilityRole="alert" style={[ks.notice, { backgroundColor: '#FFF0EE' }]}>
                  <Icon name="alert-circle-outline" color={C.red} />
                  <Text style={[s.body, { flex: 1, color: '#9B2226' }]}>{error}</Text>
                  <Button title="Retry" small secondary onPress={() => void act(refresh)} />
                </View>
              ) : null}

              <View style={{ flexDirection: wide ? 'row' : 'column', gap: 26, flex: 1 }}>
                <View style={{ flex: 1, gap: 18 }}>
                  {!offer ? (
                    <>
                      <View style={{ gap: 12, paddingTop: 6 }}>
                        <Text
                          style={{
                            fontSize: wide ? 42 : 36,
                            lineHeight: wide ? 48 : 42,
                            fontWeight: '700',
                            color: C.ink,
                          }}
                        >
                          A little sorting.{'\n'}A lot of good.
                        </Text>
                        <Text style={[s.body, { fontSize: 17, lineHeight: 26 }]}>
                          What are you dropping off today?
                        </Text>
                      </View>
                      <View style={{ flexDirection: width >= 570 ? 'row' : 'column', gap: 18 }}>
                        {(['recyclable', 'food'] as Category[]).map((category) => {
                          const full = station?.compartments[category].full;
                          const disabled =
                            busy || !station || !station.online || station.busy || full;
                          return (
                            <Pressable
                              key={category}
                              accessibilityRole="button"
                              accessibilityLabel={`Choose ${LABEL[category]}${full ? ', bin full' : ''}`}
                              disabled={disabled}
                              onPress={() => choose(category)}
                              style={({ pressed }) => [
                                ks.choice,
                                {
                                  backgroundColor: category === 'food' ? C.peach : C.greenBg,
                                  opacity: disabled ? 0.5 : 1,
                                  transform: [{ translateY: pressed ? 2 : 0 }],
                                  borderColor: pressed
                                    ? category === 'food'
                                      ? '#B66532'
                                      : C.green
                                    : 'transparent',
                                },
                              ]}
                            >
                              <View style={[s.between, { alignItems: 'flex-start' }]}>
                                <MaterialArt category={category} size={130} />
                                <View style={ks.arrow}>
                                  <Icon name="arrow-forward" color={C.ink} size={22} />
                                </View>
                              </View>
                              <View style={{ gap: 10 }}>
                                <Text style={{ fontSize: 28, fontWeight: '700', color: C.ink }}>
                                  {LABEL[category]}
                                </Text>
                                <Text
                                  style={[
                                    s.body,
                                    { color: category === 'food' ? '#744A30' : '#315A3E' },
                                  ]}
                                >
                                  {category === 'food'
                                    ? 'Fruit peels, leftovers & food scraps'
                                    : 'Clean bottles, cans & dry paper'}
                                </Text>
                              </View>
                              <View style={[s.between, { marginTop: 12, gap: 10 }]}>
                                <Text
                                  style={{
                                    color: category === 'food' ? '#744A30' : '#315A3E',
                                    fontWeight: '600',
                                  }}
                                >
                                  {full
                                    ? 'Full · awaiting collection'
                                    : `${station?.points_per_kg[category] ?? (category === 'food' ? 50 : 100)} points / kg`}
                                </Text>
                                <Icon
                                  name={full ? 'lock-closed-outline' : 'checkmark-circle-outline'}
                                  color={category === 'food' ? '#744A30' : '#315A3E'}
                                />
                              </View>
                            </Pressable>
                          );
                        })}
                      </View>
                      <View style={[ks.notice, { backgroundColor: 'white' }]}>
                        <Icon name="scan-outline" color={C.red} size={25} />
                        <Text style={[s.body, { flex: 1 }]}>
                          Choose your category, scan the QR with your phone, then place your items
                          on the weighing plate.
                        </Text>
                      </View>
                      {station?.busy && (
                        <Text accessibilityRole="alert" style={[s.body, { color: C.orange }]}>
                          Someone is using this station. Your turn is coming up.
                        </Text>
                      )}
                    </>
                  ) : (
                    <View style={[ks.panel, { flex: 1, gap: 24, padding: wide ? 36 : 24 }]}>
                      <View style={[s.between, { gap: 10 }]}>
                        <View style={[s.row, { gap: 8 }]}>
                          <Icon
                            name={selected === 'food' ? 'nutrition-outline' : 'leaf-outline'}
                            color={selected === 'food' ? '#965428' : C.green}
                          />
                          <Text style={s.h3}>{LABEL[selected]} only</Text>
                        </View>
                        {!verified && !checking && !terminal && (
                          <Pressable
                            accessibilityRole="button"
                            onPress={() =>
                              void act(async () => {
                                await kioskRequest(`/api/kiosk/offers/${offer.id}/cancel`, {});
                                reset();
                              })
                            }
                            style={{ padding: 8 }}
                          >
                            <Text style={{ color: C.muted }}>Cancel</Text>
                          </Pressable>
                        )}
                      </View>
                      {offer.state === 'completed' ? (
                        <View style={ks.center}>
                          <View style={[ks.success, { backgroundColor: C.greenBg }]}>
                            <Icon name="checkmark" color={C.green} size={42} />
                          </View>
                          <Text style={ks.flowTitle}>A little good, done.</Text>
                          <Text style={{ fontSize: 58, fontWeight: '700', color: C.green }}>
                            +{offer.deposit?.points} <Text style={{ fontSize: 20 }}>points</Text>
                          </Text>
                          <Text style={[s.body, { textAlign: 'center' }]}>
                            {offer.deposit?.weight_kg} kg of {LABEL[selected].toLowerCase()},
                            sorted. Your points are already in your account.
                          </Text>
                          <Button title="Ready for the next person" onPress={reset} />
                        </View>
                      ) : terminal ? (
                        <View style={ks.center}>
                          <Icon name="time-outline" size={54} color={C.muted} />
                          <Text style={ks.flowTitle}>
                            {expired ? 'Let’s get a fresh code.' : 'Session ended.'}
                          </Text>
                          <Text style={[s.body, { textAlign: 'center' }]}>
                            Choose a category again when you’re ready. An expired code cannot claim
                            another person’s deposit.
                          </Text>
                          <Button title="Choose a category" onPress={reset} />
                        </View>
                      ) : offer.state === 'waiting' ? (
                        <View
                          style={{
                            flexDirection: width > 1050 ? 'row' : 'column',
                            alignItems: 'center',
                            gap: 30,
                            flex: 1,
                            justifyContent: 'center',
                          }}
                        >
                          <View style={{ flex: width > 1050 ? 1 : undefined, gap: 15 }}>
                            <Text style={ks.flowTitle}>Make this drop-off yours.</Text>
                            <Text style={s.body}>
                              Scan with your phone camera or the Sime Loop app. Sign in to connect
                              your points account.
                            </Text>
                            <Text style={[s.caption, { color: '#656565' }]}>
                              Your selected bin stays closed until the camera checks your items.
                            </Text>
                          </View>
                          <View style={{ alignItems: 'center', gap: 14 }}>
                            <View style={ks.qr}>
                              {offer.claim_url ? (
                                <QRCode value={offer.claim_url} size={220} color={C.ink} />
                              ) : null}
                            </View>
                            <Text style={[s.caption, { fontVariant: ['tabular-nums'] }]}>
                              New code in {Math.floor(seconds / 60)}:
                              {String(seconds % 60).padStart(2, '0')}
                            </Text>
                            <Pressable
                              accessibilityRole="link"
                              onPress={() => {
                                if (Platform.OS === 'web' && offer.claim_url)
                                  window.open(offer.claim_url, '_blank', 'noopener,noreferrer');
                              }}
                            >
                              <Text style={{ color: C.red, textDecorationLine: 'underline' }}>
                                Open on this device
                              </Text>
                            </Pressable>
                          </View>
                        </View>
                      ) : (
                        <View style={ks.center}>
                          {checking || verified ? (
                            <ActivityIndicator size="large" color={C.red} />
                          ) : (
                            <MaterialArt category={selected} size={145} />
                          )}
                          <Text style={ks.flowTitle}>
                            {checking
                              ? 'Checking your items…'
                              : verified
                                ? 'Giving your waste a new home.'
                                : alert
                                  ? 'Let’s check that again.'
                                  : `Hi, ${offer.resident_first_name || 'neighbour'}. You’re connected.`}
                          </Text>
                          <Text
                            accessibilityLiveRegion="polite"
                            style={[
                              s.body,
                              {
                                textAlign: 'center',
                                maxWidth: 510,
                                color: alert ? '#9B2226' : C.body,
                              },
                            ]}
                          >
                            {checking
                              ? 'Keep your hands clear. The camera will check the selected category before the door opens.'
                              : verified
                                ? 'Only your selected door opens. Your points arrive after sorting and weighing are confirmed.'
                                : alert
                                  ? offer.deposit?.verification_message
                                  : `Place your ${LABEL[selected].toLowerCase()} on the weighing plate, with every item visible. Then tap below.`}
                          </Text>
                          {!checking && !verified && (
                            <Button
                              title="Check my items"
                              icon="camera-outline"
                              loading={busy}
                              onPress={() =>
                                void act(async () => {
                                  await kioskRequest(`/api/kiosk/offers/${offer.id}/check`, {});
                                  await refresh();
                                })
                              }
                            />
                          )}
                          {checking && (
                            <Pressable
                              accessibilityRole="button"
                              onPress={() =>
                                void act(async () => {
                                  await kioskRequest(`/api/kiosk/offers/${offer.id}/check`, {});
                                  await refresh();
                                })
                              }
                              style={{ minHeight: 44, justifyContent: 'center' }}
                            >
                              <Text style={{ color: C.muted }}>
                                Taking a while? Request a new check
                              </Text>
                            </Pressable>
                          )}
                        </View>
                      )}
                    </View>
                  )}
                </View>

                <View
                  style={{
                    width: wide ? 290 : '100%',
                    gap: 22,
                    paddingTop: wide && !offer ? 6 : 0,
                  }}
                >
                  <View style={[ks.panel, { gap: 22 }]}>
                    <View style={[s.row, { gap: 9 }]}>
                      <Icon name="podium-outline" color={C.red} />
                      <Text style={s.h2}>Local good-makers</Text>
                    </View>
                    <Text style={[s.caption, { marginTop: -12 }]}>
                      {station?.demo_mode ? 'Sample leaderboard' : station?.township || 'City of Elmina'} · all-time points
                    </Text>
                    {station?.leaderboard.length ? (
                      station.leaderboard.map((person) => (
                        <View key={person.rank} style={[s.between, { gap: 12 }]}>
                          <View style={[s.row, { flex: 1, gap: 12 }]}>
                            <Text
                              style={{
                                width: 20,
                                fontWeight: '700',
                                color: person.rank === 1 ? '#98671C' : C.muted,
                              }}
                            >
                              {person.rank}
                            </Text>
                            <View
                              style={[
                                ks.avatar,
                                {
                                  backgroundColor: ['#FFF0D1', '#EAF4EC', '#FFF0E6'][
                                    Math.min(person.rank - 1, 2)
                                  ],
                                },
                              ]}
                            >
                              <Text style={{ fontWeight: '600', color: C.ink }}>
                                {person.name[0]}
                              </Text>
                            </View>
                            <Text
                              style={{ flex: 1, fontWeight: '500', color: C.ink }}
                              numberOfLines={1}
                            >
                              {person.name}
                            </Text>
                          </View>
                          <Text
                            style={{
                              fontWeight: '700',
                              color: C.ink,
                              fontVariant: ['tabular-nums'],
                            }}
                          >
                            {person.points.toLocaleString('en-MY')}
                          </Text>
                        </View>
                      ))
                    ) : (
                      <Text style={s.body}>
                        {station
                          ? 'Be the first to make a difference here.'
                          : 'Connecting to your community…'}
                      </Text>
                    )}
                  </View>
                  <View style={{ paddingHorizontal: 4, gap: 13 }}>
                    <Text style={s.h3}>A little room for more</Text>
                    {(['recyclable', 'food', 'reject'] as const).map((category) => {
                      const level = station?.compartments[category];
                      return (
                        <View key={category} style={{ gap: 8 }}>
                          <View style={s.between}>
                            <Text style={s.caption}>
                              {category === 'reject' ? 'Rejected waste' : LABEL[category]}
                            </Text>
                            <Text
                              style={{
                                fontSize: 12,
                                fontWeight: '600',
                                color: level?.full ? C.red : C.green,
                              }}
                            >
                              {level
                                ? level.full
                                  ? 'Full · collection requested'
                                  : 'Available'
                                : 'Connecting'}
                            </Text>
                          </View>
                          <View style={{ height: 4, backgroundColor: '#E0E2DC', borderRadius: 3 }}>
                            <View
                              style={{
                                height: 4,
                                width: `${level?.fill_percent || 0}%`,
                                backgroundColor: level?.full ? C.red : C.green,
                                borderRadius: 3,
                              }}
                            />
                          </View>
                        </View>
                      );
                    })}
                    <Text style={[s.caption, { marginTop: 3 }]}>
                      If one bin is full, the other available bins can still be used.
                    </Text>
                  </View>
                </View>
              </View>
              <View
                style={[
                  s.between,
                  {
                    gap: 12,
                    flexWrap: 'wrap',
                    paddingTop: 14,
                    borderTopWidth: 1,
                    borderColor: C.border,
                  },
                ]}
              >
                <View style={[s.row, { gap: 7 }]}>
                  <View
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: 4,
                      backgroundColor: station?.online ? C.green : C.muted,
                    }}
                  />
                  <Text style={s.caption}>
                    {station?.online ? 'Station online' : 'Connecting to station'} · {stationId}
                  </Text>
                </View>
                <Text style={s.caption}>Sort. Scan. Do a little good.</Text>
                {station?.demo_mode && (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => setDemo(!demo)}
                    style={{ minHeight: 44, justifyContent: 'center' }}
                  >
                    <Text style={{ color: '#7A621F', fontSize: 12 }}>
                      {demo ? 'Hide prototype demo' : 'Try without hardware'}
                    </Text>
                  </Pressable>
                )}
              </View>
              {demo && (
                <View style={[ks.notice, { backgroundColor: C.yellow, flexWrap: 'wrap' }]}>
                  <Text style={[s.caption, { width: '100%', color: '#705A22' }]}>
                    Prototype simulation · no camera or hardware runs. Use the demo resident
                    account.
                  </Text>
                  {!offer ? (
                    <Text style={s.body}>Choose a category above first.</Text>
                  ) : (
                    <>
                      <Button
                        small
                        secondary
                        title="Connect demo resident"
                        disabled={busy || offer.state !== 'waiting'}
                        onPress={() => demoAction('connect')}
                      />
                      <Button
                        small
                        secondary
                        title="Simulate matching items"
                        disabled={busy || !offer.deposit || terminal}
                        onPress={() => demoAction('match')}
                      />
                      <Button
                        small
                        secondary
                        title="Simulate wrong category"
                        disabled={busy || !offer.deposit || terminal}
                        onPress={() => demoAction('mismatch')}
                      />
                      <Button
                        small
                        title="Simulate 500 g deposit"
                        disabled={
                          busy ||
                          offer.deposit?.status !== 'classified' ||
                          offer.deposit?.model !== 'demo-simulation' ||
                          terminal
                        }
                        onPress={() => demoAction('complete')}
                      />
                    </>
                  )}
                </View>
              )}
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const ks = StyleSheet.create({
  panel: {
    backgroundColor: 'white',
    borderRadius: 18,
    padding: 24,
    borderWidth: 1,
    borderColor: '#E9E9E6',
  },
  choice: {
    flex: 1,
    minHeight: 280,
    padding: 22,
    borderRadius: 18,
    gap: 14,
    borderWidth: 2,
    justifyContent: 'space-between',
  },
  notice: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 18, borderRadius: 12 },
  arrow: {
    width: 42,
    height: 42,
    backgroundColor: '#FFFFFF99',
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  settings: {
    width: 44,
    height: 44,
    backgroundColor: 'white',
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: C.border,
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  center: { flex: 1, minHeight: 350, alignItems: 'center', justifyContent: 'center', gap: 20 },
  flowTitle: {
    fontSize: 32,
    lineHeight: 39,
    fontWeight: '700',
    color: C.ink,
    textAlign: 'center',
    maxWidth: 530,
  },
  qr: {
    padding: 20,
    borderRadius: 16,
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: C.border,
  },
  success: {
    width: 84,
    height: 84,
    borderRadius: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
