export type User = {
  id: string;
  name: string;
  email: string;
  role: 'resident' | 'cleaner';
  township: string;
  points: number;
  lifetime_points: number;
};
export type Bin = {
  id: string;
  name: string;
  township: string;
  address: string;
  latitude: number;
  longitude: number;
  food_fill: number;
  recycle_fill: number;
  reject_fill: number;
  accepting_deposits: boolean;
  status: 'available' | 'full' | 'in_use' | 'offline';
  qr_payload: string;
  last_seen: string;
};
export type Voucher = {
  id: string;
  merchant: string;
  title: string;
  description: string;
  location: string;
  cost: number;
  category: string;
  color: string;
  stock: number;
};
export type WalletItem = Voucher & {
  voucher_id: string;
  code: string;
  status: 'available' | 'used' | 'expired';
  created_at: string;
  expires_at: string;
};
export type Transaction = {
  id: string;
  title: string;
  subtitle: string;
  type: 'earned' | 'redeemed' | 'rejected';
  points: number;
  weight_kg: number;
  created_at: string;
};
export type Rank = {
  id: string;
  name: string;
  township?: string;
  points: number;
  members?: number;
  rank: number;
};
export type Notice = {
  id: string;
  title: string;
  body: string;
  kind: string;
  is_read: number;
  created_at: string;
};
export type Deposit = {
  id: string;
  bin_id: string;
  status: 'pending' | 'classified' | 'completed' | 'expired' | 'cancelled';
  category: string | null;
  material: string | null;
  confidence: number | null;
  model: string | null;
  points: number;
  weight_kg: number | null;
  expires_at: string;
  selected_category?: 'food' | 'recyclable' | null;
  capture_requested?: number;
  verification_message?: string | null;
};
export type Classification = {
  category: string;
  material: string;
  confidence: number;
  model: string;
  accepted: boolean;
  route: string;
  message: string;
  is_demo: boolean;
};
export type Task = {
  id: string;
  bin_id: string;
  name: string;
  township: string;
  address: string;
  latitude: number;
  longitude: number;
  compartment: 'food' | 'recyclable' | 'reject';
  status: 'open' | 'acknowledged' | 'resolved';
  acknowledged_by: string | null;
  created_at: string;
  food_fill: number;
  recycle_fill: number;
  reject_fill: number;
};
export type Dashboard = {
  user: User;
  stats: { total_kg: number; recycled_kg: number; food_kg: number; visits: number; rank: number };
  active_session: Deposit | null;
  demo_mode: boolean;
};
export type Shift = { today: string; location: string; schedule: { day: string; hours: string }[] };
