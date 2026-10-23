import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
  BackHandler,
  Image,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { StatusBar } from 'expo-status-bar';
import Constants from 'expo-constants';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import * as Notifications from 'expo-notifications';
import QRCode from 'react-native-qrcode-svg';
import {
  useFonts,
  DMSans_400Regular,
  DMSans_500Medium,
  DMSans_600SemiBold,
  DMSans_700Bold,
  DMSans_800ExtraBold,
} from '@expo-google-fonts/dm-sans';
import { DEFAULT_API, request, requestId } from './src/api';
import Kiosk from './src/Kiosk';
import {
  Bin,
  Classification,
  Dashboard,
  Deposit,
  Notice,
  Rank,
  Shift,
  Task,
  Transaction,
  User,
  Voucher,
  WalletItem,
} from './src/types';
import {
  CleanerScreen,
  DashboardScreen,
  HistoryScreen,
  LeaderboardScreen,
  Page,
  ProfileScreen,
  RewardsScreen,
  ScreenProps,
} from './src/screens';
import {
  Avatar,
  Badge,
  Brand,
  Button,
  C,
  EcoArt,
  Empty,
  Icon,
  IconName,
  Text,
  fmt,
  s,
} from './src/ui';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});
const STORAGE = 'simeloop-session-v1';
const NAV: { name: Page; icon: IconName; active: IconName }[] = [
  { name: 'Dashboard', icon: 'grid-outline', active: 'grid' },
  { name: 'Rewards', icon: 'gift-outline', active: 'gift' },
  { name: 'History', icon: 'time-outline', active: 'time' },
  { name: 'Leaderboard', icon: 'podium-outline', active: 'podium' },
  { name: 'Profile', icon: 'person-outline', active: 'person' },
];

type Data = {
  dashboard: Dashboard;
  bins: Bin[];
  vouchers: Voucher[];
  wallet: WalletItem[];
  history: Transaction[];
  ranks: Rank[];
  townshipRanks: Rank[];
  notices: Notice[];
  tasks: Task[];
  shift: Shift | null;
};
type Sheet = 'scan' | 'reward' | 'wallet' | 'notifications' | 'photo' | 'qr' | 'profile' | null;

export default function App() {
  useFonts({
    DMSans_400Regular,
    DMSans_500Medium,
    DMSans_600SemiBold,
    DMSans_700Bold,
    DMSans_800ExtraBold,
  });
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      {process.env.EXPO_PUBLIC_SURFACE === 'kiosk' ||
      (Platform.OS === 'web' &&
        typeof window !== 'undefined' &&
        window.location.pathname.startsWith('/kiosk')) ? (
        <Kiosk />
      ) : (
        <LoopApp />
      )}
    </SafeAreaProvider>
  );
}

function LoopApp() {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const desktop = width >= 1000;
  const [base, setBase] = useState(DEFAULT_API);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [data, setData] = useState<Data | null>(null);
  const [page, setPage] = useState<Page>('Dashboard');
  const [sheet, setSheet] = useState<Sheet>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [refreshing, setRefreshing] = useState(false);
  const [offline, setOffline] = useState(false);
  const [toast, setToast] = useState<{ message: string; error: boolean } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seenNotices = useRef<Set<string> | null>(null);
  const remotePush = useRef(false);
  const hasLoaded = useRef(false);
  const scroll = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const [selectedVoucher, setSelectedVoucher] = useState<Voucher | null>(null);
  const [selectedWallet, setSelectedWallet] = useState<WalletItem | null>(null);
  const [selectedBin, setSelectedBin] = useState<Bin | null>(null);
  const [deposit, setDeposit] = useState<Deposit | null>(null);
  const [result, setResult] = useState<Classification | null>(null);
  const [weight, setWeight] = useState('0.5');
  const [camera, setCamera] = useState(false);
  const [permission, askPermission] = useCameraPermissions();
  const [photo, setPhoto] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [claimKey, setClaimKey] = useState(() =>
    Platform.OS === 'web' && typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('claim') || ''
      : '',
  );
  const [claimText, setClaimText] = useState('');
  const claiming = useRef(false);
  const redemptionRequest = useRef(requestId());
  const confirmationRequest = useRef(requestId());
  const showToast = useCallback((message: string, error = false) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ message, error });
    toastTimer.current = setTimeout(() => setToast(null), error ? 10000 : 5500);
  }, []);
  const api = useCallback(
    <T,>(path: string, body?: unknown, method?: string) =>
      request<T>(base, path, token, body, method),
    [base, token],
  );

  useEffect(() => {
    AsyncStorage.getItem(STORAGE)
      .then((saved) => {
        if (saved) {
          const session = JSON.parse(saved);
          setBase(session.base || DEFAULT_API);
          setToken(session.token);
          setUser(session.user);
        }
      })
      .catch(() => {})
      .finally(() => setBooting(false));
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const load = useCallback(async () => {
    if (!token || !user) return;
    try {
      const [
        dashboard,
        bins,
        vouchers,
        wallet,
        history,
        ranks,
        townshipRanks,
        notices,
        cleanerData,
      ] = await Promise.all([
        api<Dashboard>('/api/dashboard'),
        api<Bin[]>('/api/bins'),
        api<Voucher[]>('/api/vouchers'),
        api<WalletItem[]>('/api/wallet'),
        api<Transaction[]>('/api/history'),
        api<Rank[]>('/api/leaderboard'),
        api<Rank[]>('/api/leaderboard?scope=townships'),
        api<Notice[]>('/api/notifications'),
        user.role === 'cleaner'
          ? api<{ tasks: Task[]; shift: Shift }>('/api/cleaner/tasks')
          : Promise.resolve({ tasks: [] as Task[], shift: null }),
      ]);
      setData({
        dashboard,
        bins,
        vouchers,
        wallet,
        history,
        ranks,
        townshipRanks,
        notices,
        tasks: cleanerData.tasks,
        shift: cleanerData.shift,
      });
      setUser(dashboard.user);
      setOffline(false);
      hasLoaded.current = true;
      if (seenNotices.current && user.role === 'cleaner') {
        const fresh = notices.filter(
          (n) => n.kind === 'bin_full' && !seenNotices.current!.has(n.id),
        );
        for (const notice of fresh) {
          showToast(notice.title);
          if (Platform.OS !== 'web' && !remotePush.current)
            Notifications.scheduleNotificationAsync({
              content: { title: notice.title, body: notice.body, sound: true },
              trigger: null,
            }).catch(() => {});
        }
      }
      seenNotices.current = new Set(notices.map((n) => n.id));
    } catch (err) {
      setOffline(true);
      if (!hasLoaded.current) showToast((err as Error).message, true);
    }
  }, [token, user?.id, user?.role, api, showToast]);

  useEffect(() => {
    if (token) {
      void load();
      const timer = setInterval(() => {
        if (AppState.currentState === 'active' || Platform.OS === 'web') void load();
      }, 8000);
      return () => clearInterval(timer);
    }
  }, [token, load]);
  useEffect(() => {
    if (!claimKey || !token || !data || claiming.current || user?.role !== 'resident') return;
    claiming.current = true;
    void api<Deposit>('/api/kiosk/claim', { key: claimKey })
      .then(async (d) => {
        setDeposit(d);
        setSelectedBin(data.bins.find((b) => b.id === d.bin_id) || null);
        setSheet('scan');
        setCamera(false);
        setResult(null);
        await load();
        if (Platform.OS === 'web' && typeof window !== 'undefined')
          window.history.replaceState({}, '', window.location.pathname);
        showToast(
          `Connected for ${d.selected_category === 'food' ? 'food waste' : 'recyclables'}. Follow the bin screen.`,
        );
      })
      .catch((err) => showToast((err as Error).message, true))
      .finally(() => {
        setClaimKey('');
        claiming.current = false;
      });
  }, [claimKey, token, !!data, user?.role, api]);
  useEffect(() => {
    if (Platform.OS !== 'web') {
      const sub = BackHandler.addEventListener('hardwareBackPress', () => {
        if (sheet) {
          setSheet(null);
          return true;
        }
        if (page !== 'Dashboard') {
          setPage('Dashboard');
          return true;
        }
        return false;
      });
      return () => sub.remove();
    }
  }, [sheet, page]);
  useEffect(() => {
    if (
      sheet !== 'scan' ||
      !deposit ||
      ['completed', 'cancelled', 'expired'].includes(deposit.status)
    )
      return;
    const timer = setInterval(() => {
      api<Deposit>(`/api/deposits/${deposit.id}`)
        .then((d) => {
          setDeposit(d);
          if (d.status === 'completed') {
            showToast(`Nice work! ${d.points} points are now in your account.`);
            void load();
          }
        })
        .catch(() => {});
    }, 2500);
    return () => clearInterval(timer);
  }, [sheet, deposit?.id, deposit?.status, api, load]);

  async function action(work: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      await work();
    } catch (err) {
      showToast((err as Error).message || 'Something went wrong. Please try again.', true);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function signIn(email: string, password: string, address: string) {
    await action(async () => {
      const signed = await request<{ token: string; user: User }>(
        address,
        '/api/auth/login',
        null,
        { email, password },
      );
      await AsyncStorage.setItem(STORAGE, JSON.stringify({ ...signed, base: address }));
      setBase(address);
      setToken(signed.token);
      setUser(signed.user);
      setData(null);
      setPage('Dashboard');
      seenNotices.current = null;
      hasLoaded.current = false;
      if (Platform.OS !== 'web' && signed.user.role === 'cleaner') {
        if (Platform.OS === 'android')
          await Notifications.setNotificationChannelAsync('default', {
            name: 'Bin collections',
            importance: Notifications.AndroidImportance.HIGH,
          });
        const granted = await Notifications.requestPermissionsAsync();
        const projectId =
          process.env.EXPO_PUBLIC_EAS_PROJECT_ID ||
          Constants.easConfig?.projectId ||
          Constants.expoConfig?.extra?.eas?.projectId;
        if (granted.status === 'granted' && projectId) {
          try {
            const pushToken = await Notifications.getExpoPushTokenAsync({ projectId });
            const registration = await request<{ enabled: boolean }>(
              address,
              '/api/push-tokens',
              signed.token,
              { token: pushToken.data },
            );
            remotePush.current = registration.enabled;
          } catch {
            showToast(
              'Background notifications need a configured native build. Your collection queue remains available.',
            );
          }
        }
      }
    });
  }
  async function logout() {
    await action(async () => {
      try {
        await api('/api/auth/logout', {});
      } catch {
        /* Local sign-out remains available offline. */
      }
      await AsyncStorage.removeItem(STORAGE);
      setToken(null);
      setUser(null);
      setData(null);
      setSheet(null);
      setDeposit(null);
      seenNotices.current = null;
      remotePush.current = false;
      hasLoaded.current = false;
    });
  }
  function go(next: Page) {
    setPage(next);
    scroll.current?.scrollTo({ y: 0, animated: false });
  }
  function close() {
    setSheet(null);
    setCamera(false);
  }
  function openScan(bin?: Bin) {
    setDeposit(data?.dashboard.active_session || null);
    setSelectedBin(bin || null);
    setResult(null);
    setCamera(false);
    setSheet('scan');
    confirmationRequest.current = requestId();
  }
  function openReward(v: Voucher) {
    setSelectedVoucher(v);
    redemptionRequest.current = requestId();
    setSheet('reward');
  }
  function openNotifications() {
    setSheet('notifications');
    void api('/api/notifications/read', {})
      .then(load)
      .catch(() => {});
  }
  function startDeposit(binId: string) {
    if (
      !binId.startsWith('simeloop://bin/') &&
      (binId.includes('claim=') || binId.startsWith('simeloop://claim/'))
    ) {
      try {
        const key = binId.startsWith('simeloop://claim/')
          ? binId.slice('simeloop://claim/'.length)
          : new URL(binId).searchParams.get('claim');
        if (!key) throw new Error('Scan the current QR code on the bin screen.');
        setClaimKey(key);
        setCamera(false);
      } catch {
        showToast('This is not a valid station QR. Scan the current code on the bin screen.', true);
      }
      return;
    }
    void action(async () => {
      const d = await api<Deposit>('/api/deposits', { bin_id: binId });
      setDeposit(d);
      setCamera(false);
      setResult(null);
      await load();
    });
  }
  async function pickPhoto(take = false) {
    await action(async () => {
      if (take && Platform.OS !== 'web') {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted)
          throw new Error(
            'Camera access is off. Enable it in your phone settings or choose a photo.',
          );
      }
      const picked =
        take && Platform.OS !== 'web'
          ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.75 })
          : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.75 });
      if (picked.canceled) return;
      const image = picked.assets[0];
      setPhoto(image.uri);
      setResult(null);
      const form = new FormData();
      if (Platform.OS === 'web') {
        const blob = await (await fetch(image.uri)).blob();
        form.append('file', blob, image.fileName || 'waste.jpg');
      } else
        form.append('file', {
          uri: image.uri,
          name: image.fileName || 'waste.jpg',
          type: image.mimeType || 'image/jpeg',
        } as unknown as Blob);
      const classification = await api<Classification>('/api/vision/classify', form);
      setResult(classification);
    });
  }

  const cleaner = user?.role === 'cleaner';
  const nav = cleaner ? NAV.filter((n) => ['Dashboard', 'Profile'].includes(n.name)) : NAV;
  const subtitles: Record<Page, string> = {
    Dashboard: cleaner
      ? 'Keep your neighbourhood moving, one collection at a time.'
      : 'A little good for your neighbourhood. A little good for you.',
    Rewards: 'Good habits deserve good things.',
    History: 'Every small action leaves a positive trail.',
    Leaderboard: 'Greener communities grow together.',
    Profile: 'Your place in a greener community.',
  };
  const greeting = user
    ? `Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening'}, ${user.name.split(' ')[0]}`
    : '';
  const props: ScreenProps | null =
    data && user
      ? {
          ...data,
          user,
          busy,
          go,
          scan: openScan,
          redeem: openReward,
          showWallet: (item) => {
            setSelectedWallet(item || null);
            setSheet('wallet');
          },
          checkPhoto: () => {
            setResult(null);
            setPhoto(null);
            setSheet('photo');
          },
          showQr: (bin) => {
            setSelectedBin(bin);
            setSheet('qr');
          },
          taskAction: (task) => {
            void action(async () => {
              await api(
                `/api/cleaner/tasks/${task.id}/${task.status === 'open' ? 'acknowledge' : 'resolve'}`,
                {},
              );
              await load();
              showToast(
                task.status === 'open'
                  ? 'Task accepted. Thank you for taking care of your area.'
                  : 'Collection recorded. This compartment is ready again.',
              );
            });
          },
          demoFill: () => {
            void action(async () => {
              await api('/api/demo/fill', {
                bin_id: 'ELM-01',
                compartment: 'food',
                fill_percent: 95,
              });
              await load();
              showToast('Demo sensor reading sent. A collection alert is now in the queue.');
            });
          },
          editProfile: () => {
            setEditName(user.name);
            setSheet('profile');
          },
          logout: () => {
            void logout();
          },
          notify: openNotifications,
        }
      : null;

  if (booting)
    return (
      <View style={styles.loading}>
        <Brand />
        <ActivityIndicator color={C.red} />
      </View>
    );
  if (!token || !user)
    return (
      <>
        <Login busy={busy} initialBase={base} signIn={signIn} />
        {toast && <Toast toast={toast} dismiss={() => setToast(null)} />}
      </>
    );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top', 'left', 'right']}>
      <View style={{ flex: 1, flexDirection: 'row' }}>
        {desktop && (
          <View style={styles.sidebar}>
            <View style={{ paddingHorizontal: 27, paddingTop: 34, paddingBottom: 42 }}>
              <Brand />
            </View>
            <View style={{ gap: 7, paddingHorizontal: 17 }}>
              {nav.map((n) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ selected: page === n.name }}
                  key={n.name}
                  onPress={() => go(n.name)}
                  style={({ pressed }) => [
                    styles.navItem,
                    page === n.name && { backgroundColor: '#FFF0EC' },
                    pressed && { opacity: 0.6 },
                  ]}
                >
                  <Icon
                    name={page === n.name ? n.active : n.icon}
                    color={page === n.name ? C.red : C.muted}
                    size={20}
                  />
                  <Text
                    style={{
                      fontSize: 13,
                      color: page === n.name ? C.red : C.muted,
                      fontWeight: page === n.name ? '700' : '500',
                      flex: 1,
                    }}
                  >
                    {cleaner && n.name === 'Dashboard' ? 'Collections' : n.name}
                  </Text>
                  {n.name === 'Rewards' && (
                    <View style={{ backgroundColor: '#F9E4D9', padding: 4, borderRadius: 4 }}>
                      <Text style={{ fontSize: 9, color: C.darkRed }}>PERKS</Text>
                    </View>
                  )}
                </Pressable>
              ))}
            </View>
            <View style={{ flex: 1 }} />
            <View
              style={{
                padding: 20,
                margin: 17,
                backgroundColor: '#F8F7F1',
                borderRadius: 13,
                gap: 10,
              }}
            >
              <Icon
                name={cleaner ? 'shield-checkmark-outline' : 'leaf-outline'}
                color={C.green}
                size={26}
              />
              <Text style={s.h3}>{cleaner ? 'Every collection counts.' : 'Better, together.'}</Text>
              <Text style={s.caption}>
                {cleaner
                  ? 'You help keep good habits going in your community.'
                  : 'One neighbourhood. Thousands of small, good choices.'}
              </Text>
              {!cleaner && (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => {
                    setResult(null);
                    setPhoto(null);
                    setSheet('photo');
                  }}
                  style={{ minHeight: 35, justifyContent: 'center' }}
                >
                  <Text style={{ fontSize: 11, color: C.green, fontWeight: '700' }}>
                    A little help sorting ↗
                  </Text>
                </Pressable>
              )}
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={() => go('Profile')}
              style={{
                padding: 20,
                borderTopWidth: 1,
                borderColor: C.border,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 10,
              }}
            >
              <Avatar name={user.name} size={36} />
              <View style={{ flex: 1 }}>
                <Text style={[s.h3, { fontSize: 12 }]}>{user.name}</Text>
                <Text style={s.caption}>{cleaner ? 'Cleaner / guard' : 'Community resident'}</Text>
              </View>
              <Icon name="chevron-forward" size={14} />
            </Pressable>
            <Text style={{ marginHorizontal: 25, marginBottom: 21, fontSize: 9, color: C.muted }}>
              Inspired by Sime Darby Property{'\n'}Hackathon concept · Demo community
            </Text>
          </View>
        )}
        <View style={{ flex: 1 }}>
          <View style={[styles.topbar, { paddingHorizontal: desktop ? 40 : 20 }]}>
            {desktop ? (
              <View style={s.row}>
                <Text style={s.caption}>Your community</Text>
                <Icon name="chevron-forward" size={11} />
                <Text style={{ fontSize: 11, color: C.ink }}>
                  {cleaner && page === 'Dashboard' ? 'Collections' : page}
                </Text>
              </View>
            ) : (
              <Brand compact />
            )}
            <View style={[s.row, { gap: desktop ? 20 : 12 }]}>
              {!cleaner && (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => go('Rewards')}
                  style={{
                    flexDirection: 'row',
                    gap: 6,
                    alignItems: 'center',
                    backgroundColor: '#FFF4E8',
                    borderRadius: 20,
                    paddingHorizontal: 13,
                    height: 34,
                  }}
                >
                  <Icon name="sparkles" size={13} color={C.orange} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: '#9F551D' }}>
                    {fmt(user.points)} pts
                  </Text>
                </Pressable>
              )}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Notifications"
                onPress={openNotifications}
                style={styles.iconButton}
              >
                <Icon name="notifications-outline" size={22} />
                {!!data?.notices.some((n) => !n.is_read) && (
                  <View
                    style={{
                      position: 'absolute',
                      top: 9,
                      right: 10,
                      width: 6,
                      height: 6,
                      backgroundColor: C.red,
                      borderRadius: 4,
                      borderWidth: 1,
                      borderColor: 'white',
                    }}
                  />
                )}
              </Pressable>
              {desktop && <Avatar name={user.name} size={34} />}
            </View>
          </View>
          {offline && (
            <Pressable
              accessibilityRole="button"
              onPress={() => void load()}
              style={{ backgroundColor: C.yellow, padding: 12 }}
            >
              <Text style={{ color: '#795F18', fontSize: 12, textAlign: 'center' }}>
                Connection interrupted. Showing the last update. Tap to retry.
              </Text>
            </Pressable>
          )}
          <ScrollView
            ref={scroll}
            style={{ flex: 1 }}
            contentContainerStyle={{ padding: desktop ? 34 : 20, paddingTop: desktop ? 30 : 24 }}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                tintColor={C.red}
                onRefresh={async () => {
                  setRefreshing(true);
                  await load();
                  setRefreshing(false);
                }}
              />
            }
          >
            <View style={{ width: '100%', maxWidth: 1360, alignSelf: 'center' }}>
              <View style={[s.between, { marginBottom: 26, alignItems: 'flex-start' }]}>
                <View style={{ flex: 1, gap: 7 }}>
                  <Text style={[s.h1, !desktop && { fontSize: 26 }]}>
                    {page === 'Dashboard'
                      ? `${greeting}.`
                      : page === 'Rewards'
                        ? 'Good things come full circle.'
                        : page === 'History'
                          ? 'Your story, one sort at a time.'
                          : page === 'Leaderboard'
                            ? 'A community of good.'
                            : 'Hello, neighbour.'}
                  </Text>
                  <Text style={s.body}>{subtitles[page]}</Text>
                </View>
                {desktop && (
                  <View style={[s.row, { marginTop: 6 }]}>
                    <Icon name="location-outline" size={15} />
                    <Text style={s.caption}>{user.township}</Text>
                  </View>
                )}
              </View>
              {!props ? (
                <View style={{ padding: 60, gap: 22, alignItems: 'center' }}>
                  <ActivityIndicator color={C.red} />
                  <Text style={s.body}>Bringing your community together…</Text>
                  {offline && (
                    <>
                      <Button title="Try again" onPress={() => void load()} />
                      <Button
                        title="Return to sign in"
                        secondary
                        onPress={() => {
                          setToken(null);
                          setUser(null);
                          void AsyncStorage.removeItem(STORAGE);
                        }}
                      />
                    </>
                  )}
                </View>
              ) : page === 'Dashboard' ? (
                cleaner ? (
                  <CleanerScreen {...props} />
                ) : (
                  <DashboardScreen {...props} />
                )
              ) : page === 'Rewards' ? (
                <RewardsScreen {...props} />
              ) : page === 'History' ? (
                <HistoryScreen {...props} />
              ) : page === 'Leaderboard' ? (
                <LeaderboardScreen {...props} />
              ) : (
                <ProfileScreen {...props} />
              )}
              <View
                style={[
                  s.between,
                  {
                    paddingVertical: 16,
                    borderTopWidth: 1,
                    borderColor: C.border,
                    flexWrap: 'wrap',
                  },
                ]}
              >
                <Text style={s.caption}>Small acts. Lasting change.</Text>
                <View style={[s.row, { gap: 5 }]}>
                  <View
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: 3,
                      backgroundColor: offline ? C.orange : C.green,
                    }}
                  />
                  <Text style={s.caption}>
                    {data?.dashboard.demo_mode ? 'Hackathon demo' : 'Community live'} ·{' '}
                    {offline ? 'Reconnecting' : 'Connected to bin service'}
                  </Text>
                </View>
              </View>
            </View>
          </ScrollView>
          {!desktop && (
            <View
              style={{
                flexDirection: 'row',
                backgroundColor: 'white',
                borderTopWidth: 1,
                borderColor: C.border,
                paddingTop: 8,
                paddingBottom: Math.max(insets.bottom, 10),
              }}
            >
              {nav.map((n) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={n.name}
                  accessibilityState={{ selected: page === n.name }}
                  key={n.name}
                  onPress={() => go(n.name)}
                  style={{
                    flex: 1,
                    minHeight: 49,
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 4,
                  }}
                >
                  <Icon
                    name={page === n.name ? n.active : n.icon}
                    color={page === n.name ? C.red : C.muted}
                    size={21}
                  />
                  <Text
                    style={{
                      color: page === n.name ? C.red : C.muted,
                      fontSize: 9,
                      fontWeight: page === n.name ? '700' : '400',
                    }}
                  >
                    {cleaner && n.name === 'Dashboard' ? 'Collections' : n.name}
                  </Text>
                </Pressable>
              ))}
            </View>
          )}
        </View>
      </View>
      <SheetView
        visible={sheet !== null}
        close={close}
        title={
          sheet === 'scan'
            ? 'Your next little act of good'
            : sheet === 'reward'
              ? 'Make those points a treat'
              : sheet === 'wallet'
                ? 'Your voucher wallet'
                : sheet === 'notifications'
                  ? 'Good things to know'
                  : sheet === 'photo'
                    ? 'Where does this item go?'
                    : sheet === 'profile'
                      ? 'Make yourself at home'
                      : 'Station QR code'
        }
      >
        {sheet === 'reward' && selectedVoucher && (
          <View style={{ gap: 20 }}>
            <View
              style={{
                backgroundColor: selectedVoucher.color,
                padding: 26,
                borderRadius: 13,
                gap: 8,
              }}
            >
              <Icon name="ticket-outline" color={C.ink} size={35} />
              <Text style={[s.h2, { fontSize: 27 }]}>{selectedVoucher.merchant}</Text>
              <Text style={s.h3}>{selectedVoucher.title}</Text>
            </View>
            <Text style={s.body}>{selectedVoucher.description}</Text>
            <View style={s.between}>
              <Text style={s.body}>Redeem for</Text>
              <Text style={{ fontSize: 22, fontWeight: '700', color: C.red }}>
                {fmt(selectedVoucher.cost)} pts
              </Text>
            </View>
            <View style={s.between}>
              <Text style={s.body}>Your balance after redemption</Text>
              <Text style={s.h3}>{fmt(user.points - selectedVoucher.cost)} pts</Text>
            </View>
            <Text style={s.caption}>
              {selectedVoucher.location} · Valid for 30 days. This hackathon voucher is a
              demonstration and has no cash value.
            </Text>
            <Button
              title="Confirm redemption"
              loading={busy}
              disabled={user.points < selectedVoucher.cost}
              onPress={() => {
                void action(async () => {
                  const redeemed = await api<WalletItem>(
                    `/api/vouchers/${selectedVoucher.id}/redeem`,
                    { request_id: redemptionRequest.current },
                  );
                  await load();
                  setSelectedWallet({ ...selectedVoucher, ...redeemed });
                  setSheet('wallet');
                  showToast('Your reward is ready. Find the code in your wallet.');
                });
              }}
            />
          </View>
        )}
        {sheet === 'wallet' && (
          <View style={{ gap: 16 }}>
            {selectedWallet ? (
              <>
                <View
                  style={{
                    backgroundColor: selectedWallet.color,
                    padding: 25,
                    borderRadius: 13,
                    gap: 8,
                  }}
                >
                  <Text style={s.h2}>{selectedWallet.merchant}</Text>
                  <Text style={s.h3}>{selectedWallet.title}</Text>
                  <Text style={s.body}>{selectedWallet.location}</Text>
                </View>
                <Badge
                  label={selectedWallet.status}
                  color={selectedWallet.status === 'available' ? C.green : C.muted}
                  bg={selectedWallet.status === 'available' ? C.greenBg : C.bg}
                />
                <View style={{ alignItems: 'center', padding: 20, gap: 18 }}>
                  {selectedWallet.status === 'available' && (
                    <QRCode value={selectedWallet.code} size={160} color={C.ink} />
                  )}
                  <Text
                    selectable
                    style={{ fontSize: 22, fontWeight: '700', letterSpacing: 2, color: C.ink }}
                  >
                    {selectedWallet.code}
                  </Text>
                  <Text style={s.caption}>
                    Expires {new Date(selectedWallet.expires_at).toLocaleDateString('en-MY')}
                  </Text>
                </View>
                <Text style={s.caption}>
                  Demo voucher only. In a live rollout, a merchant would validate this code at
                  checkout.
                </Text>
                {data?.dashboard.demo_mode && selectedWallet.status === 'available' && (
                  <Button
                    title="Demo: mark voucher as used"
                    secondary
                    loading={busy}
                    onPress={() => {
                      void action(async () => {
                        await api(`/api/demo/wallet/${selectedWallet.id}/use`, {});
                        setSelectedWallet({ ...selectedWallet, status: 'used' });
                        await load();
                        showToast('Voucher marked as used in this demo.');
                      });
                    }}
                  />
                )}
                <Button
                  title="Back to all vouchers"
                  secondary
                  onPress={() => setSelectedWallet(null)}
                />
              </>
            ) : data?.wallet.length ? (
              data.wallet.map((v) => (
                <Pressable
                  accessibilityRole="button"
                  key={v.id}
                  onPress={() => setSelectedWallet(v)}
                  style={[s.card, { padding: 18, gap: 10 }]}
                >
                  <View style={s.between}>
                    <Text style={s.h3}>{v.merchant}</Text>
                    <Badge
                      label={v.status}
                      color={v.status === 'available' ? C.green : C.muted}
                      bg={v.status === 'available' ? C.greenBg : C.bg}
                    />
                  </View>
                  <Text style={s.body}>{v.title}</Text>
                  <Text style={s.caption}>
                    Expires {new Date(v.expires_at).toLocaleDateString('en-MY')} · View code ↗
                  </Text>
                </Pressable>
              ))
            ) : (
              <Empty
                icon="ticket-outline"
                title="A little treat is waiting to happen"
                text="Redeem a reward with your Loop points and it will appear here."
              />
            )}
          </View>
        )}
        {sheet === 'notifications' && (
          <View>
            {data?.notices.length ? (
              data.notices.map((n) => (
                <View
                  key={n.id}
                  style={{
                    flexDirection: 'row',
                    gap: 13,
                    paddingVertical: 18,
                    borderBottomWidth: 1,
                    borderColor: C.border,
                  }}
                >
                  <Icon
                    name={
                      n.kind === 'bin_full'
                        ? 'alert-circle-outline'
                        : n.kind === 'points'
                          ? 'sparkles-outline'
                          : 'leaf-outline'
                    }
                    color={C.red}
                  />
                  <View style={{ flex: 1, gap: 5 }}>
                    <Text style={s.h3}>{n.title}</Text>
                    <Text style={s.body}>{n.body}</Text>
                    <Text style={s.caption}>{new Date(n.created_at).toLocaleString('en-MY')}</Text>
                  </View>
                </View>
              ))
            ) : (
              <Empty
                icon="notifications-outline"
                title="You're all caught up"
                text="Points, rewards and community updates will appear here."
              />
            )}
          </View>
        )}
        {sheet === 'qr' && selectedBin && (
          <View style={{ alignItems: 'center', gap: 20, paddingVertical: 10 }}>
            <Text style={s.h2}>{selectedBin.name}</Text>
            <Text style={s.body}>
              {selectedBin.id} · {selectedBin.township}
            </Text>
            <View style={{ padding: 24, backgroundColor: 'white', borderRadius: 16 }}>
              <QRCode value={selectedBin.qr_payload} size={220} color={C.ink} />
            </View>
            <Text selectable style={s.caption}>
              {selectedBin.qr_payload}
            </Text>
            <Text style={[s.body, { textAlign: 'center' }]}>
              Print this QR for the station. Residents scan it with Sime Loop to begin a deposit.
            </Text>
            <Button title="Use this station" onPress={() => openScan(selectedBin)} />
          </View>
        )}
        {sheet === 'profile' && (
          <View style={{ gap: 18 }}>
            <Text style={s.body}>How should your neighbours see your name?</Text>
            <TextInput
              accessibilityLabel="Your name"
              value={editName}
              onChangeText={setEditName}
              style={s.input}
              maxLength={60}
            />
            <Button
              title="Save name"
              loading={busy}
              disabled={editName.trim().length < 2}
              onPress={() => {
                void action(async () => {
                  await api('/api/me', { name: editName.trim() }, 'PATCH');
                  await load();
                  close();
                  showToast('Your name has been updated.');
                });
              }}
            />
          </View>
        )}
        {sheet === 'photo' && (
          <View style={{ gap: 18 }}>
            <Text style={s.body}>
              One item, a clear photo. Our image model suggests whether it belongs with food waste
              or clean recyclables.
            </Text>
            {photo && (
              <Image
                source={{ uri: photo }}
                style={{ height: 220, width: '100%', borderRadius: 12 }}
                resizeMode="contain"
              />
            )}
            <View style={[s.row, { flexWrap: 'wrap' }]}>
              <Button
                title={photo ? 'Choose another photo' : 'Choose a photo'}
                icon="images-outline"
                loading={busy}
                onPress={() => void pickPhoto()}
              />
              {Platform.OS !== 'web' && (
                <Button
                  title="Take a photo"
                  icon="camera-outline"
                  secondary
                  loading={busy}
                  onPress={() => void pickPhoto(true)}
                />
              )}
            </View>
            {busy && (
              <Text style={s.body}>
                Checking with the image model. The first check can take a little longer.
              </Text>
            )}
            {result && (
              <View
                style={{
                  backgroundColor: result.accepted ? C.greenBg : C.yellow,
                  padding: 20,
                  borderRadius: 12,
                  gap: 9,
                }}
              >
                <Text style={s.h2}>
                  {result.category === 'food'
                    ? 'Food waste'
                    : result.category === 'recyclable'
                      ? 'Clean recyclables'
                      : result.accepted && result.route === 'reject'
                        ? 'Mixed waste · no points'
                        : 'Needs a closer look'}
                </Text>
                <Text style={s.body}>{result.message}</Text>
                <Text style={s.caption}>
                  Best match: {result.material} · Model score {Math.round(result.confidence * 100)}%
                </Text>
              </View>
            )}
            <Text style={s.caption}>
              Model scores are estimates, not a guarantee of recyclability. Follow local collection
              rules. Photo checks do not award points; the station must verify a physical deposit.
            </Text>
          </View>
        )}
        {sheet === 'scan' && (
          <View style={{ gap: 18 }}>
            {!deposit ? (
              <>
                <Text style={s.body}>
                  Scan the QR on a nearby station, or choose one below. Keep your food scraps
                  separate from clean recyclables.
                </Text>
                {camera ? (
                  permission?.granted ? (
                    <View style={{ height: 270, borderRadius: 14, overflow: 'hidden' }}>
                      <CameraView
                        style={{ flex: 1 }}
                        facing="back"
                        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
                        onBarcodeScanned={({ data }) => {
                          if (!lock.current) startDeposit(data);
                        }}
                      />
                    </View>
                  ) : (
                    <Text style={s.body}>
                      Camera permission is needed to scan. You can also select a station below.
                    </Text>
                  )
                ) : (
                  <Button
                    title="Open QR scanner"
                    icon="scan-outline"
                    onPress={() => {
                      void action(async () => {
                        if (!permission?.granted) {
                          const asked = await askPermission();
                          if (!asked.granted) {
                            showToast(
                              'Camera permission is off. Select a station below, or enable camera access in settings.',
                              true,
                            );
                            return;
                          }
                        }
                        setCamera(true);
                      });
                    }}
                  />
                )}
                {selectedBin && (
                  <View style={{ padding: 14, backgroundColor: C.peach, borderRadius: 10 }}>
                    <Text style={s.h3}>{selectedBin.name}</Text>
                    <Text style={s.caption}>{selectedBin.address}</Text>
                  </View>
                )}
                <View style={{ gap: 10 }}>
                  <Text style={s.h3}>Scan the code on the bin screen</Text>
                  <Text style={s.caption}>
                    Choose food waste or recyclables on the station first. Each QR connects one
                    drop-off to your account. You can also paste its link below.
                  </Text>
                  <TextInput
                    accessibilityLabel="Station QR link"
                    value={claimText}
                    onChangeText={setClaimText}
                    autoCapitalize="none"
                    placeholder="Paste the station QR link"
                    style={s.input}
                  />
                  <Button
                    title="Connect to this drop-off"
                    secondary
                    disabled={busy || !claimText.trim()}
                    onPress={() => startDeposit(claimText.trim())}
                  />
                </View>
                <Text style={s.h3}>
                  {selectedBin ? 'Start at this station' : 'Or choose a station'}
                </Text>
                {(selectedBin ? [selectedBin] : data?.bins || []).map((bin) => (
                  <Pressable
                    key={bin.id}
                    accessibilityRole="button"
                    disabled={busy || bin.status === 'in_use' || bin.status === 'offline'}
                    onPress={() => startDeposit(bin.id)}
                    style={[
                      s.card,
                      {
                        padding: 16,
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 13,
                        opacity: bin.status === 'in_use' || bin.status === 'offline' ? 0.4 : 1,
                      },
                    ]}
                  >
                    <Icon name="location-outline" color={C.red} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.h3}>{bin.name}</Text>
                      <Text style={s.caption}>
                        {bin.id} · {bin.township}
                      </Text>
                    </View>
                    <Icon name="chevron-forward" size={16} />
                  </Pressable>
                ))}
              </>
            ) : deposit.status === 'completed' ? (
              <View style={{ alignItems: 'center', gap: 18, padding: 24 }}>
                <View style={{ backgroundColor: C.greenBg, borderRadius: 45, padding: 20 }}>
                  <Icon name="checkmark" size={42} color={C.green} />
                </View>
                <Text style={s.h2}>That’s a little good, done.</Text>
                <Text style={{ fontSize: 42, fontWeight: '700', color: C.green }}>
                  +{deposit.points} <Text style={{ fontSize: 18 }}>pts</Text>
                </Text>
                <Text style={[s.body, { textAlign: 'center' }]}>
                  {deposit.weight_kg} kg of{' '}
                  {deposit.category === 'food'
                    ? 'food waste diverted'
                    : deposit.category === 'reject'
                      ? 'mixed waste collected'
                      : 'recyclables given a second life'}
                  .{' '}
                  {deposit.category === 'reject'
                    ? 'Mixed waste earns no points. Sort it first next time.'
                    : 'Your points are already in your account.'}
                </Text>
                <Button title="Keep the good going" onPress={close} />
              </View>
            ) : ['expired', 'cancelled'].includes(deposit.status) ? (
              <>
                <Empty
                  title="This deposit session has ended"
                  text="Start a fresh session when you are ready to recycle."
                />
                <Button
                  title="Choose a station"
                  onPress={() => {
                    setDeposit(null);
                    setResult(null);
                  }}
                />
              </>
            ) : (
              <>
                <Badge
                  label={
                    deposit.status === 'classified'
                      ? 'Item verified · waiting for deposit'
                      : 'Connected to station'
                  }
                />
                <Text style={s.h2}>
                  {data?.bins.find((b) => b.id === deposit.bin_id)?.name || deposit.bin_id}
                </Text>
                <Text style={s.body}>
                  {deposit.selected_category
                    ? `This drop-off is for ${deposit.selected_category === 'food' ? 'food waste' : 'recyclables'} only. Place your items on the weighing plate, then press Check my items on the bin screen. The door stays closed if anything does not match.`
                    : 'Choose a category on the bin screen and scan its QR. The camera checks your items before the selected door opens. Points arrive after weighing and sorting are confirmed.'}
                </Text>
                {!!deposit.verification_message && (
                  <Text
                    accessibilityLiveRegion="polite"
                    style={[s.body, { color: deposit.status === 'pending' ? C.red : C.green }]}
                  >
                    {deposit.verification_message}
                  </Text>
                )}
                <View style={{ backgroundColor: C.bg, borderRadius: 12, padding: 20, gap: 10 }}>
                  <View style={s.row}>
                    <Icon
                      name={
                        deposit.status === 'classified'
                          ? 'checkmark-circle-outline'
                          : 'camera-outline'
                      }
                      color={deposit.status === 'classified' ? C.green : C.muted}
                    />
                    <Text style={s.h3}>
                      {deposit.status === 'classified'
                        ? `Route: ${deposit.category === 'food' ? 'food waste' : deposit.category === 'reject' ? 'rejected waste · no points' : 'recyclables'}`
                        : deposit.category === 'reject'
                          ? 'Please remove the mixed or unclear item'
                          : 'Waiting for the station camera…'}
                    </Text>
                  </View>
                  {deposit.material && (
                    <Text style={s.body}>
                      {deposit.material}
                      {deposit.confidence
                        ? ` · ${Math.round(deposit.confidence * 100)}% model score`
                        : ''}
                    </Text>
                  )}
                  <Text style={s.caption}>
                    Session {deposit.id.slice(0, 8)} · expires{' '}
                    {new Date(deposit.expires_at).toLocaleTimeString('en-MY', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
                {data?.dashboard.demo_mode && (
                  <View
                    style={{ backgroundColor: C.yellow, borderRadius: 13, padding: 20, gap: 15 }}
                  >
                    <View style={s.row}>
                      <Icon name="flask-outline" color="#8A6C23" />
                      <Text style={s.h3}>Try the hardware-free demo</Text>
                    </View>
                    <Text style={s.caption}>
                      Simulated item and weight readings. This demonstration does not run the image
                      model.
                    </Text>
                    <View style={[s.row, { flexWrap: 'wrap' }]}>
                      {[
                        ['recyclable', 'Clean bottle'],
                        ['food', 'Fruit peels'],
                        ['reject', 'Mixed waste'],
                      ].map(([category, label]) => (
                        <Button
                          key={category}
                          title={label}
                          small
                          secondary
                          disabled={busy}
                          onPress={() => {
                            void action(async () => {
                              const r = await api<Classification>(
                                `/api/demo/deposits/${deposit.id}/classify`,
                                { category },
                              );
                              setResult(r);
                              setDeposit(await api<Deposit>(`/api/deposits/${deposit.id}`));
                            });
                          }}
                        />
                      ))}
                    </View>
                    {result && (
                      <Text style={s.body}>
                        {result.accepted
                          ? `Demo item accepted. Route: ${result.route}.`
                          : 'Item rejected. Separate mixed waste and try a single item.'}
                      </Text>
                    )}
                    {deposit.status === 'classified' && deposit.model === 'demo-simulation' && (
                      <>
                        <View style={s.row}>
                          <Text style={s.body}>Simulated weight (kg)</Text>
                          <TextInput
                            accessibilityLabel="Simulated weight in kilograms"
                            keyboardType="decimal-pad"
                            value={weight}
                            onChangeText={setWeight}
                            style={[s.input, { width: 100 }]}
                          />
                        </View>
                        <Button
                          title={
                            deposit.category === 'reject'
                              ? 'Simulate reject disposal (0 points)'
                              : 'Simulate deposit & earn points'
                          }
                          loading={busy}
                          onPress={() => {
                            void action(async () => {
                              const kg = Number(weight);
                              if (!Number.isFinite(kg) || kg < 0.01 || kg > 4)
                                throw new Error('Enter a weight between 0.01 and 4 kg.');
                              const d = await api<Deposit>(
                                `/api/demo/deposits/${deposit.id}/confirm`,
                                { weight_kg: kg, event_id: confirmationRequest.current },
                              );
                              setDeposit(d);
                              await load();
                              showToast(`You earned ${d.points} points. Nice work!`);
                            });
                          }}
                        />
                      </>
                    )}
                  </View>
                )}
                <Button
                  title="Cancel this deposit"
                  secondary
                  loading={busy}
                  onPress={() => {
                    void action(async () => {
                      await api(`/api/deposits/${deposit.id}/cancel`, {});
                      setDeposit(null);
                      setResult(null);
                      await load();
                    });
                  }}
                />
              </>
            )}
          </View>
        )}
      </SheetView>
      {toast && <Toast toast={toast} dismiss={() => setToast(null)} />}
    </SafeAreaView>
  );
}

function Login({
  busy,
  initialBase,
  signIn,
}: {
  busy: boolean;
  initialBase: string;
  signIn: (email: string, password: string, address: string) => Promise<void>;
}) {
  const { width } = useWindowDimensions();
  const [email, setEmail] = useState('resident@simeloop.demo');
  const [password, setPassword] = useState('Loop123!');
  const [base, setBase] = useState(initialBase);
  const [settings, setSettings] = useState(false);
  const wide = width > 850;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: 'white' }}>
      <ScrollView contentContainerStyle={{ flexGrow: 1 }}>
        <View style={{ flex: 1, flexDirection: wide ? 'row' : 'column' }}>
          <View
            style={{
              flex: wide ? 1.1 : undefined,
              backgroundColor: C.peach,
              padding: wide ? 60 : 28,
              justifyContent: 'space-between',
              minHeight: wide ? 700 : 280,
            }}
          >
            <Brand />
            <View style={{ marginVertical: wide ? 40 : 24 }}>
              <Text
                style={{
                  color: C.ink,
                  fontWeight: '700',
                  letterSpacing: -1.7,
                  fontSize: wide ? 52 : 34,
                  lineHeight: wide ? 59 : 40,
                }}
              >
                Good things{'\n'}come full circle.
              </Text>
              <Text
                style={{
                  color: '#705948',
                  fontSize: 15,
                  lineHeight: 25,
                  marginTop: 20,
                  maxWidth: 340,
                }}
              >
                A simpler way to recycle. A little reward for doing good. A greener place to call
                home.
              </Text>
              {wide && (
                <View style={{ alignItems: 'center', marginTop: 18 }}>
                  <EcoArt width={330} />
                </View>
              )}
            </View>
            <Text style={{ fontSize: 11, color: '#7E6552' }}>
              A community recycling concept inspired by Sime Darby Property.
            </Text>
          </View>
          <View
            style={{
              flex: 1,
              padding: wide ? 60 : 26,
              justifyContent: 'center',
              alignItems: 'center',
            }}
          >
            <View style={{ width: '100%', maxWidth: 390, gap: 22 }}>
              <View style={{ gap: 10 }}>
                <Text style={[s.h1, { fontSize: 30 }]}>Hello, neighbour.</Text>
                <Text style={s.body}>Step into your greener everyday.</Text>
              </View>
              <View style={{ gap: 9 }}>
                <Text style={s.h3}>Email address</Text>
                <TextInput
                  accessibilityLabel="Email address"
                  autoCapitalize="none"
                  keyboardType="email-address"
                  value={email}
                  onChangeText={setEmail}
                  style={s.input}
                />
              </View>
              <View style={{ gap: 9 }}>
                <Text style={s.h3}>Password</Text>
                <TextInput
                  accessibilityLabel="Password"
                  secureTextEntry
                  value={password}
                  onChangeText={setPassword}
                  style={s.input}
                  onSubmitEditing={() => void signIn(email, password, base)}
                />
              </View>
              <Button
                title="Sign in to Sime Loop"
                loading={busy}
                icon="arrow-forward"
                onPress={() => void signIn(email, password, base)}
              />
              <View style={[s.row, { gap: 12 }]}>
                <View style={[s.divider, { flex: 1 }]} />
                <Text style={s.caption}>EXPLORE THE HACKATHON DEMO</Text>
                <View style={[s.divider, { flex: 1 }]} />
              </View>
              <View style={{ gap: 10 }}>
                <Button
                  title="Try as a resident"
                  icon="leaf-outline"
                  secondary
                  loading={busy}
                  onPress={() => void signIn('resident@simeloop.demo', 'Loop123!', base)}
                />
                <Button
                  title="Try as a cleaner / guard"
                  icon="shield-checkmark-outline"
                  secondary
                  loading={busy}
                  onPress={() => void signIn('cleaner@simeloop.demo', 'Loop123!', base)}
                />
              </View>
              <Pressable
                accessibilityRole="button"
                onPress={() => setSettings(!settings)}
                style={{ minHeight: 44, justifyContent: 'center' }}
              >
                <Text style={[s.caption, { textAlign: 'center' }]}>
                  Connection settings <Icon name="chevron-down" size={11} />
                </Text>
              </Pressable>
              {settings && (
                <View style={{ gap: 10 }}>
                  <Text style={s.caption}>Backend URL (use your computer’s LAN IP on a phone)</Text>
                  <TextInput
                    accessibilityLabel="Backend API address"
                    value={base}
                    onChangeText={setBase}
                    autoCapitalize="none"
                    style={s.input}
                  />
                  <Text style={s.caption}>Test accounts use password Loop123!</Text>
                </View>
              )}
              <Text style={[s.caption, { textAlign: 'center' }]}>Sort. Drop. Earn. Repeat.</Text>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function SheetView({
  visible,
  close,
  title,
  children,
}: {
  visible: boolean;
  close: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={close}>
      <View
        style={{
          flex: 1,
          justifyContent: width > 700 ? 'center' : 'flex-end',
          alignItems: 'center',
          padding: width > 700 ? 24 : 0,
        }}
      >
        <Pressable
          accessibilityLabel="Close dialog"
          onPress={close}
          style={[StyleSheet.absoluteFill, { backgroundColor: '#1D241F80' }]}
        />
        <View
          accessibilityViewIsModal
          style={{
            backgroundColor: 'white',
            width: '100%',
            maxWidth: 600,
            maxHeight: height * 0.91,
            borderRadius: width > 700 ? 22 : 22,
            paddingBottom: width > 700 ? 0 : insets.bottom,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 24,
              paddingTop: 16,
              paddingBottom: 12,
              borderBottomWidth: 1,
              borderColor: C.border,
            }}
          >
            <Text style={[s.h2, { flex: 1 }]}>{title}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close dialog"
              onPress={close}
              style={styles.iconButton}
            >
              <Icon name="close" size={24} />
            </Pressable>
          </View>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 24 }}>
            {children}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function Toast({
  toast,
  dismiss,
}: {
  toast: { message: string; error: boolean };
  dismiss: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      onPress={dismiss}
      style={{
        position: 'absolute',
        left: 20,
        right: 20,
        bottom: Platform.OS === 'web' ? 28 : 85,
        alignSelf: 'center',
        maxWidth: 560,
        backgroundColor: toast.error ? C.darkRed : '#244D39',
        padding: 18,
        borderRadius: 12,
        zIndex: 100,
        flexDirection: 'row',
        gap: 12,
        boxShadow: '0 6px 24px #00000024',
      }}
    >
      <Icon
        name={toast.error ? 'alert-circle-outline' : 'checkmark-circle-outline'}
        color="white"
      />
      <Text style={{ color: 'white', fontSize: 13, lineHeight: 21, flex: 1 }}>{toast.message}</Text>
      <Icon name="close" color="white" size={16} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 30,
    backgroundColor: C.bg,
  },
  sidebar: { width: 232, backgroundColor: 'white', borderRightWidth: 1, borderColor: C.border },
  navItem: {
    minHeight: 49,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 13,
    paddingHorizontal: 17,
    borderRadius: 9,
  },
  topbar: {
    height: 78,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderColor: C.border,
  },
  iconButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
});
