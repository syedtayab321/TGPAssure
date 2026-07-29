const cors = require('cors')({ origin: true });
const functions = require('firebase-functions');
const admin = require('firebase-admin');
const Stripe = require('stripe');

admin.initializeApp();

const stripeSecret = process.env.STRIPE_SECRET_KEY || functions.config()?.stripe?.secret_key;
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET || functions.config()?.stripe?.webhook_secret;
const stripe = stripeSecret ? new Stripe(stripeSecret) : null;

const CURRENCY = (process.env.TGPA_CURRENCY || 'pkr').toLowerCase();

const FEATURE_PRICES = {
  'seismic.segd': 12000,
  'seismic.viewer': 18000,
  'seismic.qc': 26000,
  'seismic.converter': 12000,
  'seismic.receiver': 11000,
  'seismic.uphole': 9000,
  'seismic.scanner': 9000,
  'magnetic.data': 10000,
  'magnetic.qc': 18000,
  'magnetic.processing': 24000,
  'magnetic.viewer': 15000,
  'magnetic.reports': 9000,
  'electrical.data': 10000,
  'electrical.qc': 19000,
  'electrical.processing': 21000,
  'electrical.viewer': 14000,
  'electrical.reports': 8000,
  'gravity.data': 9000,
  'gravity.qc': 17000,
  'gravity.processing': 22000,
  'gravity.viewer': 13000,
  'gravity.reports': 8000,
  'vibroseis.data': 9000,
  'vibroseis.qc': 18000,
  'vibroseis.viewer': 10000,
  'vibroseis.planning': 12000,
  'geodetic.data': 9000,
  'geodetic.qc': 17000,
  'geodetic.coordinates': 12000,
  'geodetic.viewer': 10000,
  'geodetic.reports': 8000
};

const FREE_FEATURES = ['seismic.viewer'];
const ALL_FEATURES = Object.keys(FEATURE_PRICES);
const ENTERPRISE_PRICE = 175000;

function moduleForFeature(feature) {
  return String(feature || '').split('.')[0];
}

function uniqueValidFeatures(features) {
  return [...new Set(Array.isArray(features) ? features : [])].filter((key) => FEATURE_PRICES[key]);
}

function featuresForPlan(plan, selectedFeatures) {
  if (plan === 'free') return FREE_FEATURES;
  if (plan === 'enterprise_all') return ALL_FEATURES;
  if (plan === 'modular') return uniqueValidFeatures(selectedFeatures);
  return FREE_FEATURES;
}

function amountForPlan(plan, features) {
  if (plan === 'free') return 0;
  if (plan === 'enterprise_all') return ENTERPRISE_PRICE;
  return features.reduce((sum, key) => sum + FEATURE_PRICES[key], 0);
}

async function verifyFirebaseUser(req) {
  const header = req.get('authorization') || '';
  const match = header.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    throw new Error('Missing Firebase ID token.');
  }
  return await admin.auth().verifyIdToken(match[1]);
}

async function updateUserLicense(uid, data) {
  const selected = data.features || [];
  const modules = [...new Set(selected.map(moduleForFeature).filter(Boolean))];
  await admin.firestore().collection('tgpassure_users').doc(uid).set({
    uid,
    email: data.email || '',
    name: data.name || '',
    product: 'TGPAssure Desktop',
    plan: data.plan,
    license_status: 'active',
    features: selected,
    modules,
    payments: admin.firestore.FieldValue.arrayUnion(data.payment),
    updated_at: new Date().toISOString()
  }, { merge: true });
}

exports.createCheckoutSession = functions.https.onRequest((req, res) => {
  cors(req, res, async () => {
    try {
      if (req.method !== 'POST') {
        res.status(405).json({ error: 'POST required' });
        return;
      }
      if (!stripe) {
        res.status(500).json({ error: 'STRIPE_SECRET_KEY is not configured on the backend.' });
        return;
      }
      const decoded = await verifyFirebaseUser(req);
      const body = req.body || {};
      const plan = ['free', 'modular', 'enterprise_all'].includes(body.plan) ? body.plan : 'free';
      const features = featuresForPlan(plan, body.features);
      const amount = amountForPlan(plan, features);
      if (amount <= 0) {
        await updateUserLicense(decoded.uid, {
          email: decoded.email || body.email || '',
          name: body.name || decoded.name || '',
          plan: 'free',
          features,
          payment: {
            provider: 'stripe',
            status: 'free',
            plan: 'free',
            features,
            amount: 0,
            currency: CURRENCY.toUpperCase(),
            session_id: 'free',
            created_at: new Date().toISOString()
          }
        });
        res.json({ url: '', session_id: 'free', free: true });
        return;
      }

      const session = await stripe.checkout.sessions.create({
        mode: 'subscription',
        client_reference_id: decoded.uid,
        customer_email: decoded.email || body.email,
        success_url: body.success_url || 'https://checkout.stripe.com/success',
        cancel_url: body.cancel_url || 'https://checkout.stripe.com/cancel',
        line_items: [{
          quantity: 1,
          price_data: {
            currency: CURRENCY,
            product_data: {
              name: plan === 'enterprise_all' ? 'TGPAssure Enterprise All Modules' : 'TGPAssure Modular Professional',
              metadata: { product: 'TGPAssure Desktop' }
            },
            recurring: { interval: 'month' },
            unit_amount: amount * 100
          }
        }],
        metadata: {
          uid: decoded.uid,
          email: decoded.email || body.email || '',
          name: body.name || decoded.name || '',
          plan,
          features: features.join(','),
          amount: String(amount),
          currency: CURRENCY.toUpperCase()
        },
        subscription_data: {
          metadata: {
            uid: decoded.uid,
            plan,
            features: features.join(',')
          }
        }
      });
      res.json({ url: session.url, session_id: session.id });
    } catch (error) {
      res.status(400).json({ error: error.message || String(error) });
    }
  });
});

exports.stripeWebhook = functions.https.onRequest(async (req, res) => {
  if (!stripe || !webhookSecret) {
    res.status(500).send('Stripe webhook is not configured.');
    return;
  }
  let event;
  try {
    event = stripe.webhooks.constructEvent(req.rawBody, req.headers['stripe-signature'], webhookSecret);
  } catch (error) {
    res.status(400).send(`Webhook Error: ${error.message}`);
    return;
  }
  try {
    if (event.type === 'checkout.session.completed') {
      const session = event.data.object;
      const metadata = session.metadata || {};
      const uid = metadata.uid || session.client_reference_id;
      const features = uniqueValidFeatures(String(metadata.features || '').split(',').filter(Boolean));
      if (uid) {
        await updateUserLicense(uid, {
          email: metadata.email || session.customer_email || '',
          name: metadata.name || '',
          plan: metadata.plan || 'modular',
          features,
          payment: {
            provider: 'stripe',
            status: 'paid',
            plan: metadata.plan || 'modular',
            features,
            amount: Number(metadata.amount || 0),
            currency: metadata.currency || CURRENCY.toUpperCase(),
            session_id: session.id,
            subscription_id: session.subscription || '',
            customer_id: session.customer || '',
            created_at: new Date().toISOString()
          }
        });
      }
    }
    res.json({ received: true });
  } catch (error) {
    res.status(500).send(error.message || String(error));
  }
});
