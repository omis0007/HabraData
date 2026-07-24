//+------------------------------------------------------------------+
//|                                              GoldMRScalperGrid.mq5 |
//| Mean-reversion scalper + same-direction grid                       |
//| Presets: XAU | NAS100 | US30 | ATR_AUTO | Custom                   |
//+------------------------------------------------------------------+
#property copyright "MR scalper grid (multi-asset)"
#property version   "1.20"
#property strict

enum ENUM_ASSET_PROFILE
{
   ASSET_XAU=0,        // XAU / Gold (matched)
   ASSET_NAS100=1,     // NAS100 / USTEC
   ASSET_US30=2,       // US30 / DJ30
   ASSET_ATR_AUTO=3,   // Any symbol via ATR(M1)
   ASSET_CUSTOM=4      // Use manual distance inputs below
};

input group "==== Asset profile ===="
input ENUM_ASSET_PROFILE InpAssetProfile = ASSET_XAU; // Preset (overrides distances unless Custom)
input string InpSymbol           = "";          // empty = chart symbol
input double InpLot              = 0.05;        // Lot (indices often 0.10)

input group "==== Oscillators ===="
input int    InpStochPeriod      = 14;
input int    InpStochK           = 3;
input int    InpStochD           = 3;
input double InpStochOS          = 10.0;
input double InpStochOB          = 90.0;
input bool   InpUseDeMarker      = false;
input int    InpDeMPeriod        = 14;
input double InpDeMOS            = 0.30;
input double InpDeMOB            = 0.70;
input int    InpEmaPeriod        = 20;

input group "==== Distances (Custom / base; ATR_AUTO ignores fixed) ===="
input double InpStretchMin       = 14.0;        // from EMA
input double InpMove3Min         = 5.0;         // adverse M1 move over 3 bars
input double InpSoloTP           = 1.5;         // solo take-profit
input double InpBasketTP         = 0.40;        // beyond avg for basket exit
input double InpGridStep         = 6.0;         // adverse to add
input int    InpAtrPeriod        = 14;          // ATR period (ATR_AUTO)
input double InpAtrSoloTP        = 0.375;       // ATR× solo TP
input double InpAtrBasketTP      = 0.10;        // ATR× basket TP
input double InpAtrGrid          = 1.50;        // ATR× grid
input double InpAtrStretch       = 3.50;        // ATR× stretch
input double InpAtrMove3         = 1.25;        // ATR× move3

input group "==== Risk / filters ===="
input int    InpMaxPositions     = 5;
input int    InpMagic            = 20260724;
input bool   InpUseHourFilter    = true;

int hStoch = INVALID_HANDLE;
int hEma   = INVALID_HANDLE;
int hDeM   = INVALID_HANDLE;
int hAtr   = INVALID_HANDLE;

// Effective runtime distances (filled from preset / ATR)
double g_stretch=14.0, g_move3=5.0, g_soloTP=1.5, g_basketTP=0.40, g_grid=6.0;
int    g_hours[];   // allowed UTC hours; empty = all

void SetHoursGold()
{
   ArrayResize(g_hours, 12);
   int h[12]={2,3,4,5,6,9,10,11,15,16,17,18};
   for(int i=0;i<12;i++) g_hours[i]=h[i];
}

void SetHoursUSIndex()
{
   ArrayResize(g_hours, 8);
   int h[8]={13,14,15,16,17,18,19,20};
   for(int i=0;i<8;i++) g_hours[i]=h[i];
}

void ApplyFixedProfile()
{
   if(InpAssetProfile==ASSET_XAU)
   {
      g_stretch=14.0; g_move3=5.0; g_soloTP=1.5; g_basketTP=0.40; g_grid=6.0;
      SetHoursGold();
   }
   else if(InpAssetProfile==ASSET_NAS100)
   {
      g_stretch=55.0; g_move3=20.0; g_soloTP=12.0; g_basketTP=3.0; g_grid=40.0;
      SetHoursUSIndex();
   }
   else if(InpAssetProfile==ASSET_US30)
   {
      g_stretch=100.0; g_move3=35.0; g_soloTP=20.0; g_basketTP=5.0; g_grid=70.0;
      SetHoursUSIndex();
   }
   else // CUSTOM or ATR base placeholders
   {
      g_stretch=InpStretchMin; g_move3=InpMove3Min;
      g_soloTP=InpSoloTP; g_basketTP=InpBasketTP; g_grid=InpGridStep;
      ArrayResize(g_hours, 0); // Custom: HourAllowed uses gold list if filter on — set US if ATR
      if(InpAssetProfile==ASSET_ATR_AUTO) SetHoursUSIndex();
      else SetHoursGold();
   }
}

bool RefreshAtrDistances()
{
   if(InpAssetProfile!=ASSET_ATR_AUTO) return true;
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(hAtr, 0, 1, 1, atr) < 1) return false;
   double a = atr[0];
   if(a <= 0.0) return false;
   g_soloTP   = a * InpAtrSoloTP;
   g_basketTP = a * InpAtrBasketTP;
   g_grid     = a * InpAtrGrid;
   g_stretch  = a * InpAtrStretch;
   g_move3    = a * InpAtrMove3;
   return true;
}

bool HourAllowed()
{
   if(!InpUseHourFilter) return true;
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   int h = dt.hour;
   int n = ArraySize(g_hours);
   for(int i=0;i<n;i++) if(g_hours[i]==h) return true;
   return false;
}

string Sym()
{
   return (InpSymbol=="" ? _Symbol : InpSymbol);
}

int CountPositions(ENUM_POSITION_TYPE &side, double &avgPrice, double &lastPrice, datetime &lastTime)
{
   int count = 0;
   double volSum = 0.0, pxVol = 0.0;
   side = WRONG_VALUE;
   lastTime = 0;
   lastPrice = 0;
   for(int i=PositionsTotal()-1; i>=0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Sym()) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      ENUM_POSITION_TYPE t = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if(count==0) side = t;
      if(t != side) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      double p = PositionGetDouble(POSITION_PRICE_OPEN);
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      volSum += v;
      pxVol += p * v;
      count++;
      if(ot >= lastTime) { lastTime = ot; lastPrice = p; }
   }
   avgPrice = (volSum > 0 ? pxVol / volSum : 0);
   return count;
}

bool OpenTrade(ENUM_ORDER_TYPE type, double tpPrice)
{
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = Sym();
   req.volume = InpLot;
   req.type = type;
   req.price = (type==ORDER_TYPE_BUY ? SymbolInfoDouble(Sym(), SYMBOL_ASK)
                                     : SymbolInfoDouble(Sym(), SYMBOL_BID));
   req.deviation = 30;
   req.magic = InpMagic;
   req.comment = "MRScalperGrid";
   if(tpPrice > 0)
      req.tp = NormalizeDouble(tpPrice, (int)SymbolInfoInteger(Sym(), SYMBOL_DIGITS));
   req.type_filling = ORDER_FILLING_IOC;
   if(!OrderSend(req, res))
   {
      Print("OrderSend failed ", GetLastError(), " retcode=", res.retcode);
      return false;
   }
   return res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_DONE_PARTIAL;
}

void CloseAll()
{
   for(int i=PositionsTotal()-1; i>=0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Sym()) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      MqlTradeRequest req; MqlTradeResult res;
      ZeroMemory(req); ZeroMemory(res);
      req.action = TRADE_ACTION_DEAL;
      req.position = ticket;
      req.symbol = Sym();
      req.volume = PositionGetDouble(POSITION_VOLUME);
      ENUM_POSITION_TYPE t = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      req.type = (t==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
      req.price = (req.type==ORDER_TYPE_BUY ? SymbolInfoDouble(Sym(), SYMBOL_ASK)
                                            : SymbolInfoDouble(Sym(), SYMBOL_BID));
      req.deviation = 30;
      req.magic = InpMagic;
      req.type_filling = ORDER_FILLING_IOC;
      OrderSend(req, res);
   }
}

int OnInit()
{
   ApplyFixedProfile();
   hStoch = iStochastic(Sym(), PERIOD_M1, InpStochPeriod, InpStochK, InpStochD, MODE_SMA, STO_LOWHIGH);
   hEma   = iMA(Sym(), PERIOD_M1, InpEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   hDeM   = iDeMarker(Sym(), PERIOD_M1, InpDeMPeriod);
   if(InpAssetProfile==ASSET_ATR_AUTO)
   {
      hAtr = iATR(Sym(), PERIOD_M1, InpAtrPeriod);
      if(hAtr==INVALID_HANDLE) return INIT_FAILED;
   }
   if(hStoch==INVALID_HANDLE || hEma==INVALID_HANDLE) return INIT_FAILED;
   if(InpUseDeMarker && hDeM==INVALID_HANDLE) return INIT_FAILED;

   string profileName="XAU";
   if(InpAssetProfile==ASSET_NAS100) profileName="NAS100";
   else if(InpAssetProfile==ASSET_US30) profileName="US30";
   else if(InpAssetProfile==ASSET_ATR_AUTO) profileName="ATR_AUTO";
   else if(InpAssetProfile==ASSET_CUSTOM) profileName="CUSTOM";
   Print("MRScalperGrid profile=", profileName,
         " soloTP=", g_soloTP, " grid=", g_grid, " stretch=", g_stretch,
         " lot=", InpLot);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hStoch!=INVALID_HANDLE) IndicatorRelease(hStoch);
   if(hEma!=INVALID_HANDLE) IndicatorRelease(hEma);
   if(hDeM!=INVALID_HANDLE) IndicatorRelease(hDeM);
   if(hAtr!=INVALID_HANDLE) IndicatorRelease(hAtr);
}

void OnTick()
{
   static datetime lastBar = 0;
   datetime t = iTime(Sym(), PERIOD_M1, 0);
   if(t == lastBar) return;
   lastBar = t;

   if(!RefreshAtrDistances()) return;

   double stochMain[], ema[], dem[];
   ArraySetAsSeries(stochMain, true);
   ArraySetAsSeries(ema, true);
   ArraySetAsSeries(dem, true);
   if(CopyBuffer(hStoch, 0, 0, 5, stochMain) < 5) return;
   if(CopyBuffer(hEma, 0, 0, 5, ema) < 5) return;
   double demVal = 0.5;
   if(InpUseDeMarker)
   {
      if(CopyBuffer(hDeM, 0, 0, 5, dem) < 5) return;
      demVal = dem[1];
   }

   double close0 = iClose(Sym(), PERIOD_M1, 1);
   double close3 = iClose(Sym(), PERIOD_M1, 4);
   double st = stochMain[1];
   double em = ema[1];
   double move3 = close0 - close3;

   ENUM_POSITION_TYPE side;
   double avgPrice, lastPrice;
   datetime lastTime;
   int count = CountPositions(side, avgPrice, lastPrice, lastTime);

   double bid = SymbolInfoDouble(Sym(), SYMBOL_BID);
   double ask = SymbolInfoDouble(Sym(), SYMBOL_ASK);

   if(count == 1)
   {
      double openPx = avgPrice;
      if(side==POSITION_TYPE_BUY && bid >= openPx + g_soloTP) CloseAll();
      if(side==POSITION_TYPE_SELL && ask <= openPx - g_soloTP) CloseAll();
   }
   else if(count >= 2)
   {
      if(side==POSITION_TYPE_BUY && bid >= avgPrice + g_basketTP) CloseAll();
      if(side==POSITION_TYPE_SELL && ask <= avgPrice - g_basketTP) CloseAll();
   }

   count = CountPositions(side, avgPrice, lastPrice, lastTime);

   if(count > 0 && count < InpMaxPositions)
   {
      if(side==POSITION_TYPE_BUY)
      {
         double adverse = lastPrice - ask;
         if(adverse >= g_grid)
            OpenTrade(ORDER_TYPE_BUY, 0);
      }
      else if(side==POSITION_TYPE_SELL)
      {
         double adverse = bid - lastPrice;
         if(adverse >= g_grid)
            OpenTrade(ORDER_TYPE_SELL, 0);
      }
      return;
   }

   if(count > 0) return;
   if(!HourAllowed()) return;

   bool demBuy  = (!InpUseDeMarker) || (demVal <= InpDeMOS);
   bool demSell = (!InpUseDeMarker) || (demVal >= InpDeMOB);

   if(st <= InpStochOS && demBuy)
   {
      double stretch = em - close0;
      double against = -move3;
      if(stretch >= g_stretch && against >= g_move3)
         OpenTrade(ORDER_TYPE_BUY, ask + g_soloTP);
   }
   else if(st >= InpStochOB && demSell)
   {
      double stretch = close0 - em;
      double against = move3;
      if(stretch >= g_stretch && against >= g_move3)
         OpenTrade(ORDER_TYPE_SELL, bid - g_soloTP);
   }
}
