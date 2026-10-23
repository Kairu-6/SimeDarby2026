import React, { useMemo, useState } from 'react';
import { Linking, Pressable, TextInput, View, useWindowDimensions } from 'react-native';
import {
  Bin,
  Dashboard,
  Notice,
  Rank,
  Shift,
  Task,
  Transaction,
  User,
  Voucher,
  WalletItem,
} from './types';
import BinMap from './BinMap';
import {
  Avatar,
  Badge,
  Button,
  C,
  EcoArt,
  Empty,
  FillBar,
  Icon,
  IconName,
  SectionTitle,
  Text,
  fmt,
  s,
} from './ui';

export type Page = 'Dashboard' | 'Rewards' | 'History' | 'Leaderboard' | 'Profile';
export type ScreenProps = {
  user: User;
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
  busy: boolean;
  go: (page: Page) => void;
  scan: (bin?: Bin) => void;
  redeem: (v: Voucher) => void;
  showWallet: (item?: WalletItem) => void;
  checkPhoto: () => void;
  showQr: (bin: Bin) => void;
  taskAction: (task: Task) => void;
  demoFill: () => void;
  editProfile: () => void;
  logout: () => void;
  notify: () => void;
};

function Stat({
  icon,
  label,
  value,
  detail,
  tint = C.greenBg,
  color = C.green,
}: {
  icon: IconName;
  label: string;
  value: string;
  detail: string;
  tint?: string;
  color?: string;
}) {
  return (
    <View style={[s.card, { flex: 1, minWidth: 140, padding: 20, gap: 14 }]}>
      <View style={s.between}>
        <Text style={s.body}>{label}</Text>
        <View
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: tint,
          }}
        >
          <Icon name={icon} color={color} size={18} />
        </View>
      </View>
      <View>
        <Text style={{ fontSize: 28, color: C.ink, fontWeight: '700', letterSpacing: -0.8 }}>
          {value}
        </Text>
        <Text style={[s.caption, { marginTop: 5 }]}>{detail}</Text>
      </View>
    </View>
  );
}

export function VoucherCard({
  voucher: v,
  user,
  onPress,
  compact = false,
}: {
  voucher: Voucher;
  user: User;
  onPress: () => void;
  compact?: boolean;
}) {
  const enough = user.points >= v.cost;
  const icons: Record<string, IconName> = {
    'The Coffee House': 'cafe-outline',
    FamilyMart: 'storefront-outline',
    'Nando’s': 'restaurant-outline',
    'Village Grocer': 'basket-outline',
    'The Book Nook': 'book-outline',
    'Weekend Treats': 'ice-cream-outline',
  };
  return (
    <View
      style={{
        flex: 1,
        minWidth: compact ? 180 : 240,
        backgroundColor: 'white',
        borderWidth: 1,
        borderColor: C.border,
        borderRadius: 15,
        overflow: 'hidden',
      }}
    >
      <View
        style={{
          backgroundColor: v.color,
          minHeight: compact ? 98 : 132,
          padding: 20,
          justifyContent: 'space-between',
          overflow: 'hidden',
        }}
      >
        <View style={s.between}>
          <Text style={{ fontSize: 10, fontWeight: '700', color: '#51463E', letterSpacing: 0.4 }}>
            {v.category.toUpperCase()}
          </Text>
          <Icon name={icons[v.merchant] || 'gift-outline'} size={21} color="#51463E" />
        </View>
        <Text
          style={{
            color: '#372E28',
            fontSize: compact ? 20 : 25,
            fontWeight: '700',
            letterSpacing: -0.7,
            marginTop: 12,
          }}
        >
          {v.merchant}
        </Text>
        <View
          style={{
            position: 'absolute',
            width: 115,
            height: 115,
            borderRadius: 60,
            borderWidth: 18,
            borderColor: '#FFFFFF40',
            right: -29,
            top: 30,
          }}
        />
      </View>
      <View style={{ padding: 18, gap: 11 }}>
        <Text style={s.h3}>{v.title}</Text>
        <View style={[s.row, { gap: 4 }]}>
          <Icon name="location-outline" size={12} />
          <Text style={s.caption}>{v.location}</Text>
        </View>
        {!compact && <Text style={[s.caption, { minHeight: 34 }]}>{v.description}</Text>}
        <View style={[s.between, { marginTop: 3 }]}>
          <Text style={{ color: C.red, fontSize: 15, fontWeight: '700' }}>
            {fmt(v.cost)} <Text style={{ fontSize: 11, fontWeight: '500' }}>pts</Text>
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Redeem ${v.merchant} reward for ${v.cost} points`}
            disabled={v.stock === 0 || !enough || user.role !== 'resident'}
            onPress={onPress}
            style={({ pressed }) => ({
              minHeight: 40,
              paddingHorizontal: 12,
              paddingVertical: 11,
              backgroundColor: enough && v.stock > 0 ? C.peach : C.bg,
              borderRadius: 7,
              opacity: pressed ? 0.6 : 1,
            })}
          >
            <Text
              style={{
                fontSize: 11,
                fontWeight: '700',
                color: enough && v.stock > 0 ? C.red : C.muted,
              }}
            >
              {v.stock === 0
                ? 'Sold out'
                : enough
                  ? 'Redeem  ↗'
                  : `${fmt(v.cost - user.points)} more pts`}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

export function DashboardScreen(p: ScreenProps) {
  const { width } = useWindowDimensions();
  const wide = width >= 1100;
  const [selectedId, setSelectedId] = useState('ELM-01');
  const selected = p.bins.find((b) => b.id === selectedId) || p.bins[0];
  const near = p.bins.filter((b) => b.township === p.user.township);
  return (
    <View style={s.page}>
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: 20 }}>
        <View
          style={{
            flex: wide ? 2.3 : undefined,
            backgroundColor: C.peach,
            borderRadius: 18,
            padding: wide ? 30 : 24,
            minHeight: 258,
            flexDirection: 'row',
            overflow: 'hidden',
          }}
        >
          <View style={{ flex: 1, zIndex: 1, justifyContent: 'center', alignItems: 'flex-start' }}>
            <Text
              style={{
                fontSize: wide ? 34 : 29,
                color: C.ink,
                fontWeight: '700',
                letterSpacing: -1.1,
                lineHeight: wide ? 42 : 36,
              }}
            >
              Small acts.{'\n'}A greener tomorrow.
            </Text>
            <Text
              style={[s.body, { color: '#705948', maxWidth: 310, marginTop: 12, marginBottom: 22 }]}
            >
              Good things come full circle. Sort your waste, give it a second life, and get a little
              back.
            </Text>
            <Button
              title={p.dashboard.active_session ? 'Continue your deposit' : 'Scan & recycle'}
              icon="qr-code-outline"
              onPress={() => p.scan()}
            />
          </View>
          <View
            style={{
              justifyContent: 'center',
              marginRight: wide ? -12 : -60,
              opacity: wide ? 1 : 0.65,
              width: wide ? 245 : 125,
            }}
          >
            <EcoArt width={wide ? 260 : 195} />
          </View>
        </View>
        <View
          style={[
            s.card,
            { flex: wide ? 1 : undefined, minWidth: 220, justifyContent: 'space-between', gap: 20 },
          ]}
        >
          <View style={s.between}>
            <Text style={s.h3}>Your Loop points</Text>
            <Icon name="sparkles-outline" color={C.orange} />
          </View>
          <View>
            <Text style={{ fontSize: 42, fontWeight: '700', color: C.ink, letterSpacing: -1.5 }}>
              {fmt(p.user.points)}
              <Text style={{ fontSize: 13, fontWeight: '400', color: C.muted }}> pts</Text>
            </Text>
            <Text style={s.body}>Good choices. Great little rewards.</Text>
          </View>
          <View style={{ gap: 12 }}>
            <View style={{ height: 1, backgroundColor: C.border }} />
            <Pressable
              accessibilityRole="button"
              onPress={() => p.go('Rewards')}
              style={[s.between, { minHeight: 36 }]}
            >
              <Text style={{ color: C.red, fontSize: 12, fontWeight: '700' }}>
                Explore your rewards
              </Text>
              <Icon name="arrow-forward" color={C.red} size={16} />
            </Pressable>
          </View>
        </View>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
        <Stat
          icon="leaf-outline"
          label="Waste given a new life"
          value={`${p.dashboard.stats.total_kg} kg`}
          detail="Diverted through your sorted deposits"
        />
        <Stat
          icon="repeat-outline"
          label="Little habits, big impact"
          value={`${p.dashboard.stats.visits} visits`}
          detail="Every visit is a step forward"
          tint={C.peach}
          color={C.orange}
        />
        <Stat
          icon="podium-outline"
          label="Your community standing"
          value={`#${p.dashboard.stats.rank}`}
          detail={`${fmt(p.user.lifetime_points)} lifetime points earned`}
          tint={C.yellow}
          color="#967018"
        />
      </View>
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: 20 }}>
        <View style={[s.card, { flex: wide ? 1.65 : undefined, padding: 20 }]}>
          <SectionTitle title="Find your next drop-off" />
          <View style={[s.row, { marginTop: -6, marginBottom: 16, gap: 15, flexWrap: 'wrap' }]}>
            {[
              [C.green, 'Available'],
              [C.red, 'Full compartment'],
              [C.orange, 'In use'],
            ].map(([color, label]) => (
              <View key={label} style={[s.row, { gap: 5 }]}>
                <View style={{ width: 6, height: 6, backgroundColor: color, borderRadius: 3 }} />
                <Text style={s.caption}>{label}</Text>
              </View>
            ))}
          </View>
          <BinMap bins={p.bins} selected={selectedId} onSelect={(b) => setSelectedId(b.id)} />
          {selected && (
            <View style={{ marginTop: 16, gap: 12 }}>
              <View style={s.between}>
                <View style={{ flex: 1 }}>
                  <Text style={s.h3}>{selected.name}</Text>
                  <Text style={s.caption}>{selected.address}</Text>
                </View>
                <Pressable
                  onPress={() => p.showQr(selected)}
                  accessibilityRole="button"
                  accessibilityLabel={`Show QR code for ${selected.name}`}
                  style={{
                    minWidth: 44,
                    minHeight: 44,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Icon name="qr-code-outline" />
                </Pressable>
              </View>
              <View style={[wide ? s.row : null, { gap: wide ? 20 : 12 }]}>
                <FillBar value={selected.food_fill} label="Food waste" />
                <FillBar value={selected.recycle_fill} label="Recyclables" />
                <FillBar value={selected.reject_fill} label="Rejected" />
              </View>
            </View>
          )}
        </View>
        <View style={[s.card, { flex: wide ? 1 : undefined, padding: 20 }]}>
          <SectionTitle title="Around your neighbourhood" />
          <Text style={[s.body, { marginTop: -6, marginBottom: 12 }]}>{p.user.township}</Text>
          {near.map((bin, index) => (
            <View
              key={bin.id}
              style={{
                paddingVertical: 18,
                borderTopWidth: index ? 1 : 0,
                borderColor: C.border,
                gap: 12,
              }}
            >
              <View style={s.row}>
                <View
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 12,
                    backgroundColor: bin.status === 'full' ? '#FFF0EE' : C.greenBg,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Icon name="leaf-outline" color={bin.status === 'full' ? C.red : C.green} />
                </View>
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={s.h3}>{bin.name}</Text>
                  <Text style={s.caption}>
                    {bin.id} · {bin.township}
                  </Text>
                </View>
              </View>
              <View style={s.between}>
                <Badge
                  label={
                    bin.status === 'full'
                      ? 'Needs a collection'
                      : bin.status === 'in_use'
                        ? 'In use'
                        : 'Ready for your visit'
                  }
                  color={
                    bin.status === 'full' ? C.red : bin.status === 'in_use' ? C.orange : C.green
                  }
                  bg={
                    bin.status === 'full'
                      ? '#FFF0EE'
                      : bin.status === 'in_use'
                        ? C.peach
                        : C.greenBg
                  }
                />
                <Pressable
                  accessibilityRole="button"
                  onPress={() => p.scan(bin)}
                  style={{ minHeight: 44, justifyContent: 'center' }}
                >
                  <Icon name="arrow-forward" color={C.ink} size={18} />
                </Pressable>
              </View>
            </View>
          ))}
          <View
            style={{
              backgroundColor: '#F7F8F4',
              padding: 15,
              borderRadius: 10,
              gap: 8,
              marginTop: 12,
            }}
          >
            <View style={s.row}>
              <Icon name="bulb-outline" size={18} color={C.green} />
              <Text style={s.h3}>A cleaner sort starts at home.</Text>
            </View>
            <Text style={s.caption}>
              Empty and rinse containers. Keep food scraps separate. Our station checks each item
              before it goes in.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={p.checkPhoto}
              style={{ minHeight: 38, justifyContent: 'center' }}
            >
              <Text style={{ fontWeight: '700', fontSize: 11, color: C.green }}>
                Check an item with a photo ↗
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
      <View>
        <SectionTitle
          title="Your good habits have perks"
          action="See all rewards"
          onPress={() => p.go('Rewards')}
        />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
          {p.vouchers.slice(0, 3).map((v) => (
            <VoucherCard key={v.id} voucher={v} user={p.user} compact onPress={() => p.redeem(v)} />
          ))}
        </View>
        <Text style={[s.caption, { marginTop: 10 }]}>
          Hackathon preview · Illustrative rewards, subject to partner participation.
        </Text>
      </View>
    </View>
  );
}

export function RewardsScreen(p: ScreenProps) {
  const [filter, setFilter] = useState('All rewards');
  const [claimable, setClaimable] = useState(false);
  const { width } = useWindowDimensions();
  const available = p.wallet.filter((v) => v.status === 'available');
  const vouchers = p.vouchers.filter(
    (v) =>
      (filter === 'All rewards' || v.category === filter) &&
      (!claimable || (v.cost <= p.user.points && v.stock > 0)),
  );
  return (
    <View style={s.page}>
      <View
        style={[
          s.card,
          {
            backgroundColor: C.peach,
            borderColor: C.peach,
            flexDirection: width > 750 ? 'row' : 'column',
            gap: 24,
            alignItems: width > 750 ? 'center' : 'stretch',
            justifyContent: 'space-between',
          },
        ]}
      >
        <View style={{ gap: 8 }}>
          <Text style={s.h2}>A little thank you for giving back.</Text>
          <Text style={s.body}>Turn your everyday good into something to look forward to.</Text>
          <Text style={{ fontSize: 38, letterSpacing: -1, fontWeight: '700', color: C.ink }}>
            {fmt(p.user.points)}{' '}
            <Text style={{ fontSize: 14, fontWeight: '400', color: '#705948' }}>
              points to enjoy
            </Text>
          </Text>
        </View>
        <Button
          title={`My vouchers (${available.length})`}
          icon="ticket-outline"
          secondary
          onPress={() => p.showWallet()}
        />
      </View>
      {available.length > 0 && (
        <View>
          <SectionTitle
            title="Ready when you are"
            action="Open wallet"
            onPress={() => p.showWallet()}
          />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {available.slice(0, 3).map((v) => (
              <Pressable
                accessibilityRole="button"
                key={v.id}
                onPress={() => p.showWallet(v)}
                style={[
                  s.card,
                  {
                    flex: 1,
                    minWidth: 220,
                    padding: 18,
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 13,
                  },
                ]}
              >
                <Icon name="ticket-outline" color={C.red} size={26} />
                <View style={{ flex: 1 }}>
                  <Text style={s.h3}>{v.merchant}</Text>
                  <Text style={s.caption}>{v.title}</Text>
                </View>
                <Icon name="chevron-forward" size={16} />
              </Pressable>
            ))}
          </View>
        </View>
      )}
      <View>
        <SectionTitle title="Find your next little reward" />
        <View style={[s.between, { flexWrap: 'wrap', marginBottom: 20 }]}>
          <View style={[s.row, { flexWrap: 'wrap', gap: 7 }]}>
            {['All rewards', 'Food & drinks', 'Shopping', 'Lifestyle'].map((f) => (
              <Chip key={f} title={f} selected={filter === f} onPress={() => setFilter(f)} />
            ))}
          </View>
          <Pressable
            accessibilityRole="checkbox"
            accessibilityState={{ checked: claimable }}
            onPress={() => setClaimable(!claimable)}
            style={[s.row, { minHeight: 44, gap: 7 }]}
          >
            <Icon
              name={claimable ? 'checkbox' : 'square-outline'}
              color={claimable ? C.red : C.muted}
              size={17}
            />
            <Text style={s.caption}>Within my points</Text>
          </Pressable>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 20 }}>
          {vouchers.map((v) => (
            <View
              key={v.id}
              style={{ width: width > 1300 ? '31.8%' : width > 750 ? '48%' : '100%' }}
            >
              <VoucherCard voucher={v} user={p.user} onPress={() => p.redeem(v)} />
            </View>
          ))}
        </View>
        {!vouchers.length && (
          <Empty
            icon="ticket-outline"
            title="Your next reward is a few good habits away"
            text="Try another category or turn off the points filter to see more rewards."
          />
        )}
      </View>
      <Text style={s.caption}>
        Demo catalogue. Merchants and offers are illustrative; no real commercial vouchers are
        issued. Vouchers expire 30 days after redemption.
      </Text>
    </View>
  );
}

export function Chip({
  title,
  selected,
  onPress,
}: {
  title: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={{
        minHeight: 40,
        justifyContent: 'center',
        paddingHorizontal: 16,
        borderRadius: 20,
        backgroundColor: selected ? C.ink : 'white',
        borderWidth: 1,
        borderColor: selected ? C.ink : C.border,
      }}
    >
      <Text style={{ fontSize: 12, fontWeight: '500', color: selected ? 'white' : C.body }}>
        {title}
      </Text>
    </Pressable>
  );
}

export function HistoryScreen(p: ScreenProps) {
  const [filter, setFilter] = useState('All activity');
  const [month, setMonth] = useState('All months');
  const monthLabel = (date: string) =>
    new Date(date).toLocaleDateString('en-MY', { month: 'long', year: 'numeric' });
  const months = [...new Set(p.history.map((t) => monthLabel(t.created_at)))];
  const monthItems = p.history.filter(
    (t) => month === 'All months' || monthLabel(t.created_at) === month,
  );
  const filtered = monthItems.filter(
    (t) =>
      filter === 'All activity' ||
      (filter === 'Points earned' ? t.type === 'earned' : t.type === 'redeemed'),
  );
  const earned = monthItems.reduce((sum, t) => sum + Math.max(0, t.points), 0),
    spent = monthItems.reduce((sum, t) => sum + Math.abs(Math.min(0, t.points)), 0);
  return (
    <View style={s.page}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
        <Stat
          icon="add-circle-outline"
          label="Points earned"
          value={`+${fmt(earned)}`}
          detail={month === 'All months' ? 'Across your recorded activity' : month}
        />
        <Stat
          icon="ticket-outline"
          label="Points put to good use"
          value={fmt(spent)}
          detail="Redeemed for your little rewards"
          tint={C.peach}
          color={C.orange}
        />
        <Stat
          icon="wallet-outline"
          label="Ready for your next reward"
          value={fmt(p.user.points)}
          detail="Your current available balance"
          tint={C.yellow}
          color="#967018"
        />
      </View>
      <View style={s.card}>
        <SectionTitle title="Your trail of good" />
        <View style={[s.row, { flexWrap: 'wrap', marginBottom: 16 }]}>
          {['All activity', 'Points earned', 'Rewards redeemed'].map((f) => (
            <Chip key={f} title={f} selected={filter === f} onPress={() => setFilter(f)} />
          ))}
        </View>
        <View style={[s.row, { flexWrap: 'wrap', marginBottom: 20 }]}>
          {['All months', ...months].map((m) => (
            <Pressable
              key={m}
              accessibilityRole="button"
              onPress={() => setMonth(m)}
              style={{ minHeight: 40, paddingHorizontal: 10, justifyContent: 'center' }}
            >
              <Text
                style={{
                  fontSize: 12,
                  color: month === m ? C.red : C.muted,
                  fontWeight: month === m ? '700' : '400',
                }}
              >
                {m}
              </Text>
            </Pressable>
          ))}
        </View>
        {filtered.map((t) => (
          <View
            key={t.id}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingVertical: 19,
              borderTopWidth: 1,
              borderColor: C.border,
              gap: 14,
            }}
          >
            <View
              style={{
                width: 43,
                height: 43,
                borderRadius: 13,
                backgroundColor: t.type === 'earned' ? C.greenBg : C.peach,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon
                name={
                  t.type === 'earned'
                    ? 'leaf-outline'
                    : t.type === 'rejected'
                      ? 'trash-outline'
                      : 'ticket-outline'
                }
                color={t.type === 'earned' ? C.green : C.orange}
              />
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.h3}>{t.title}</Text>
              <Text style={s.caption}>
                {t.subtitle}
                {t.weight_kg > 0 ? ` · ${t.weight_kg} kg` : ''}
              </Text>
              <Text style={s.caption}>
                {new Date(t.created_at).toLocaleString('en-MY', {
                  day: 'numeric',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </Text>
            </View>
            <Text
              style={{
                fontSize: 16,
                fontWeight: '700',
                color: t.type === 'earned' ? C.green : C.ink,
              }}
            >
              {t.points > 0 ? '+' : '−'}
              {fmt(Math.abs(t.points))}
              <Text style={{ fontSize: 10 }}> pts</Text>
            </Text>
          </View>
        ))}
        {!filtered.length && (
          <Empty
            icon="time-outline"
            title="A fresh start"
            text="Your recycling visits and redeemed rewards will appear here."
          />
        )}
      </View>
    </View>
  );
}

export function LeaderboardScreen(p: ScreenProps) {
  const [scope, setScope] = useState('Residents');
  const rows = scope === 'Residents' ? p.ranks : p.townshipRanks;
  const mine = rows.find((r) =>
    scope === 'Residents' ? r.id === p.user.id : r.id === p.user.township,
  );
  return (
    <View style={s.page}>
      <View style={{ alignItems: 'center', paddingTop: 10, gap: 12 }}>
        <Text style={s.h2}>A little friendly competition. A shared greener future.</Text>
        <Text style={[s.body, { textAlign: 'center' }]}>
          Celebrating the people and places making every sort count.
        </Text>
        <View style={[s.row, { marginTop: 8 }]}>
          {['Residents', 'Townships'].map((f) => (
            <Chip key={f} title={f} selected={scope === f} onPress={() => setScope(f)} />
          ))}
        </View>
        <Text style={s.caption}>All-time points earned · Updated with each confirmed deposit</Text>
      </View>
      <View style={[s.card, { padding: 24 }]}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'center',
            alignItems: 'flex-end',
            gap: 12,
            paddingTop: 22,
            paddingBottom: 28,
          }}
        >
          {[1, 0, 2].map((index) => {
            const r = rows[index];
            if (!r) return null;
            const first = index === 0;
            return (
              <View key={r.id} style={{ flex: 1, maxWidth: 230, alignItems: 'center', gap: 9 }}>
                {first && <Icon name="trophy" color="#B88C20" size={26} />}
                <Avatar
                  name={r.name}
                  size={first ? 66 : 52}
                  color={first ? '#F6E9BC' : '#F1EFEB'}
                />
                <Text
                  numberOfLines={2}
                  style={{
                    fontSize: 13,
                    color: C.ink,
                    fontWeight: '600',
                    textAlign: 'center',
                    minHeight: 32,
                  }}
                >
                  {r.name}
                </Text>
                <Text style={{ color: C.red, fontWeight: '700', fontSize: 14 }}>
                  {fmt(r.points)} <Text style={s.caption}>pts</Text>
                </Text>
                <View
                  style={{
                    height: first ? 116 : index === 1 ? 85 : 66,
                    width: '100%',
                    backgroundColor: first ? C.yellow : '#F5F4F1',
                    borderTopLeftRadius: 11,
                    borderTopRightRadius: 11,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Text
                    style={{
                      color: first ? '#A37D23' : '#A29A8E',
                      fontWeight: '700',
                      fontSize: 35,
                    }}
                  >
                    {r.rank}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>
        <View
          style={[s.between, { paddingVertical: 12, borderBottomWidth: 1, borderColor: C.border }]}
        >
          <Text style={s.caption}>{scope === 'Residents' ? 'RESIDENT' : 'TOWNSHIP'}</Text>
          <Text style={s.caption}>LIFETIME POINTS</Text>
        </View>
        {rows.map((r) => (
          <View
            key={r.id}
            style={[
              s.row,
              {
                paddingVertical: 16,
                paddingHorizontal: 10,
                borderRadius: 10,
                backgroundColor:
                  r.id === p.user.id || r.id === p.user.township ? '#FFF4EE' : 'white',
              },
            ]}
          >
            <Text style={{ width: 22, color: C.muted, fontSize: 13 }}>{r.rank}</Text>
            <Avatar name={r.name} size={35} />
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.h3}>
                {r.name}
                {r.id === p.user.id ? ' (you)' : ''}
              </Text>
              <Text style={s.caption}>{r.township || `${r.members} residents`}</Text>
            </View>
            <Text style={{ fontWeight: '700', fontSize: 14, color: C.ink }}>
              {fmt(r.points)} <Text style={s.caption}>pts</Text>
            </Text>
          </View>
        ))}
      </View>
      {mine && (
        <View
          style={[
            s.card,
            {
              backgroundColor: C.peach,
              borderColor: C.peach,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 15,
            },
          ]}
        >
          <Icon name="ribbon-outline" color={C.red} size={30} />
          <View style={{ flex: 1 }}>
            <Text style={s.h3}>
              {scope === 'Residents'
                ? `You're #${mine.rank}. Keep your circle growing.`
                : `Your township is #${mine.rank}. Better together.`}
            </Text>
            <Text style={s.body}>Every sorted item helps your community move forward.</Text>
          </View>
        </View>
      )}
    </View>
  );
}

export function CleanerScreen(p: ScreenProps) {
  const { width } = useWindowDimensions();
  const active = p.tasks.filter((t) => t.status !== 'resolved');
  const done = p.tasks.filter((t) => t.status === 'resolved');
  const [filter, setFilter] = useState('To collect');
  const [selected, setSelected] = useState('ELM-02');
  const visible = filter === 'Completed' ? done : active;
  return (
    <View style={s.page}>
      <View
        style={[
          s.card,
          {
            backgroundColor: C.peach,
            borderColor: C.peach,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 20,
          },
        ]}
      >
        <Avatar name={p.user.name} size={68} />
        <View style={{ flex: 1, gap: 6 }}>
          <Text style={s.h2}>A clean community starts with you, {p.user.name.split(' ')[0]}.</Text>
          <Text style={s.body}>
            {p.user.township} · Today’s shift {p.shift?.today || '09:00 – 18:00'}
          </Text>
        </View>
        <Icon name="shield-checkmark-outline" size={34} color={C.red} />
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
        <Stat
          icon="notifications-outline"
          label="Ready for collection"
          value={String(active.length)}
          detail="Full compartments in your assigned area"
          tint={C.peach}
          color={C.red}
        />
        <Stat
          icon="checkmark-circle-outline"
          label="Collections completed"
          value={String(done.length)}
          detail="Thank you for keeping things moving"
        />
        <Stat
          icon="location-outline"
          label="Stations in your area"
          value={String(p.bins.filter((b) => b.township === p.user.township).length)}
          detail={p.user.township}
          tint={C.yellow}
          color="#967018"
        />
      </View>
      <View style={{ flexDirection: width >= 1100 ? 'row' : 'column', gap: 20 }}>
        <View style={[s.card, { flex: width >= 1100 ? 1 : undefined, padding: 20 }]}>
          <SectionTitle title="Your collection queue" />
          <View style={[s.row, { marginBottom: 16 }]}>
            {['To collect', 'Completed'].map((f) => (
              <Chip key={f} title={f} selected={filter === f} onPress={() => setFilter(f)} />
            ))}
          </View>
          {visible.map((t) => (
            <View
              key={t.id}
              style={{ paddingVertical: 19, borderTopWidth: 1, borderColor: C.border, gap: 13 }}
            >
              <View style={s.between}>
                <Text style={s.h3}>{t.name}</Text>
                <Badge
                  label={
                    t.status === 'resolved'
                      ? 'Cleared'
                      : t.status === 'acknowledged'
                        ? 'Accepted'
                        : 'Needs clearing'
                  }
                  color={t.status === 'open' ? C.red : C.green}
                  bg={t.status === 'open' ? '#FFF0EE' : C.greenBg}
                />
              </View>
              <Text style={s.body}>{t.address}</Text>
              <FillBar
                label={
                  t.compartment === 'food'
                    ? 'Food waste compartment'
                    : t.compartment === 'reject'
                      ? 'Rejected waste compartment'
                      : 'Recycling compartment'
                }
                value={
                  t.compartment === 'food'
                    ? t.food_fill
                    : t.compartment === 'reject'
                      ? t.reject_fill
                      : t.recycle_fill
                }
              />
              <View style={[s.between, { marginTop: 5 }]}>
                <Pressable
                  accessibilityRole="link"
                  onPress={() =>
                    Linking.openURL(
                      `https://www.google.com/maps/dir/?api=1&destination=${t.latitude},${t.longitude}`,
                    )
                  }
                  style={[s.row, { minHeight: 44 }]}
                >
                  <Icon name="navigate-outline" size={15} color={C.red} />
                  <Text style={{ color: C.red, fontSize: 12, fontWeight: '600' }}>Directions</Text>
                </Pressable>
                {t.status !== 'resolved' && (
                  <Button
                    title={t.status === 'open' ? 'Accept task' : 'Mark as cleared'}
                    small
                    loading={p.busy}
                    onPress={() => p.taskAction(t)}
                  />
                )}
              </View>
            </View>
          ))}
          {!visible.length && (
            <Empty
              icon="checkmark-circle-outline"
              title={
                filter === 'Completed'
                  ? 'Your completed collections appear here'
                  : 'All clear in your area'
              }
              text={
                filter === 'Completed'
                  ? 'Accept a task and mark the compartment cleared after collection.'
                  : 'We’ll alert you here when a compartment reaches 90% full.'
              }
            />
          )}
        </View>
        <View style={[s.card, { flex: width >= 1100 ? 1.4 : undefined, padding: 20 }]}>
          <SectionTitle title="Your area at a glance" />
          <BinMap
            bins={p.bins.filter((b) => b.township === p.user.township)}
            selected={selected}
            onSelect={(b) => setSelected(b.id)}
          />
          <View style={{ gap: 14, marginTop: 22 }}>
            <Text style={s.h3}>Your weekly schedule</Text>
            {p.shift?.schedule.map((row) => (
              <View key={row.day} style={s.between}>
                <Text style={s.body}>{row.day}</Text>
                <Text style={[s.body, { color: C.ink }]}>{row.hours}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>
      {p.dashboard.demo_mode && (
        <View
          style={[
            s.card,
            {
              flexDirection: 'row',
              alignItems: 'center',
              gap: 15,
              backgroundColor: C.yellow,
              borderColor: '#EFE3BD',
            },
          ]}
        >
          <Icon name="flask-outline" color="#896A1F" />
          <View style={{ flex: 1 }}>
            <Text style={s.h3}>Show a live bin alert</Text>
            <Text style={s.caption}>
              Demo control: simulate the Elmina Lakeside food sensor reaching 95%.
            </Text>
          </View>
          <Button title="Simulate full bin" small secondary loading={p.busy} onPress={p.demoFill} />
        </View>
      )}
    </View>
  );
}

export function ProfileScreen(p: ScreenProps) {
  const cleaner = p.user.role === 'cleaner';
  return (
    <View style={s.page}>
      <View style={[s.card, { gap: 24 }]}>
        <View style={[s.row, { gap: 20 }]}>
          <Avatar name={p.user.name} size={80} />
          <View style={{ flex: 1, gap: 8 }}>
            <Text style={s.h2}>{p.user.name}</Text>
            <Text style={s.body}>{p.user.email}</Text>
            <Badge
              label={cleaner ? 'Community cleaner / guard' : 'Community resident'}
              color={cleaner ? C.red : C.green}
              bg={cleaner ? C.peach : C.greenBg}
            />
          </View>
        </View>
        <View style={s.divider} />
        {[
          ['Location', p.user.township, 'location-outline'],
          ['Account type', cleaner ? 'Cleaner / guard' : 'Resident', 'person-outline'],
          ['Member ID', p.user.id.toUpperCase(), 'id-card-outline'],
        ].map(([label, value, icon]) => (
          <View key={label} style={[s.row, { gap: 16 }]}>
            <Icon name={icon as IconName} />
            <Text style={[s.body, { flex: 1 }]}>{label}</Text>
            <Text style={[s.h3, { fontSize: 13 }]}>{value}</Text>
          </View>
        ))}
        <Button
          title="Edit your name"
          secondary
          icon="create-outline"
          onPress={p.editProfile}
          style={{ alignSelf: 'flex-start' }}
        />
      </View>
      {!cleaner && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
          <Stat
            icon="wallet-outline"
            label="Your available points"
            value={fmt(p.user.points)}
            detail="Ready for a well-earned reward"
          />
          <Stat
            icon="ribbon-outline"
            label="Lifetime points"
            value={fmt(p.user.lifetime_points)}
            detail="Your leaderboard standing counts every point"
            tint={C.yellow}
            color="#967018"
          />
        </View>
      )}
      <View style={[s.card, { gap: 12 }]}>
        <SectionTitle title="Make it a habit" />
        {[
          ['notifications-outline', 'Your notifications', p.notify],
          ...(!cleaner
            ? [
                ['ticket-outline', 'My vouchers', () => p.showWallet()],
                ['help-circle-outline', 'Where does this item go?', p.checkPhoto],
              ]
            : []),
        ].map(([icon, title, action]) => (
          <Pressable
            key={String(title)}
            accessibilityRole="button"
            onPress={action as () => void}
            style={[s.row, { paddingVertical: 14, borderBottomWidth: 1, borderColor: C.border }]}
          >
            <Icon name={icon as IconName} />
            <Text style={[s.h3, { flex: 1, fontSize: 14 }]}>{String(title)}</Text>
            <Icon name="chevron-forward" size={16} />
          </Pressable>
        ))}
        <Pressable accessibilityRole="button" onPress={p.logout} style={[s.row, { minHeight: 48 }]}>
          <Icon name="log-out-outline" color={C.red} />
          <Text style={{ color: C.red, fontWeight: '600', fontSize: 14 }}>Sign out</Text>
        </Pressable>
      </View>
      <Text style={[s.caption, { textAlign: 'center' }]}>
        Sime Loop · Hackathon prototype{'\n'}Built around a simple idea: good things come full
        circle.
      </Text>
    </View>
  );
}
