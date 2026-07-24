//+------------------------------------------------------------------+
//|                                              GoldMRScalperGrid.mq5 |
//| Mean-reversion gold scalper + same-direction grid recovery         |
//| Reverse-engineered from live XAUUSD.pr investor history            |
//+------------------------------------------------------------------+
#property copyright "Reverse-engineered gold MR scalper"
#property version   "1.00"
#property strict

input string InpSymbol           = "";          // empty = chart symbol
input double InpLot              = 0.05;
input int    InpStochPeriod      = 14;
input int    InpStochK           = 3;
input int    InpStochD           = 3;
input double InpStochOS          = 15.0;        // oversold (tuned)
input double InpStochOB          = 85.0;        // overbought (tuned)
input int    InpEmaPeriod        = 20;
input double InpStretchMin       = 8.0;         // USD from EMA (tuned)
input double InpMove3Min         = 2.5;         // adverse M1 move over 3 bars
input double InpSoloTP           = 1.5;         // USD TP for single position
input double InpBasketTP         = 0.15;        // USD beyond avg for basket exit
input double InpGridStep         = 6.0;         // USD adverse to add
input int    InpMaxPositions     = 3;
input int    InpMagic            = 20260724;
input bool   InpUseHourFilter    = true;

int hStoch = INVALID_HANDLE;
int hEma   = INVALID_HANDLE;

bool HourAllowed()
{
   if(!InpUseHourFilter) return true;
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   int h = dt.hour;
   return (h==2||h==3||h==4||h==5||h==6||h==9||h==10||h==11||h==15||h==16||h==17||h==18);
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
      if(t != side) continue; // should not happen
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
   req.comment = "GoldMRScalperGrid";
   // Unique-ish magic-like comment time stamp; MT5 magic is fixed for management
   if(tpPrice > 0)
   {
      req.tp = NormalizeDouble(tpPrice, (int)SymbolInfoInteger(Sym(), SYMBOL_DIGITS));
   }
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
   hStoch = iStochastic(Sym(), PERIOD_M1, InpStochPeriod, InpStochK, InpStochD, MODE_SMA, STO_LOWHIGH);
   hEma   = iMA(Sym(), PERIOD_M1, InpEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(hStoch==INVALID_HANDLE || hEma==INVALID_HANDLE) return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hStoch!=INVALID_HANDLE) IndicatorRelease(hStoch);
   if(hEma!=INVALID_HANDLE) IndicatorRelease(hEma);
}

void OnTick()
{
   static datetime lastBar = 0;
   datetime t = iTime(Sym(), PERIOD_M1, 0);
   if(t == lastBar) return; // new M1 bar only
   lastBar = t;

   double stochMain[], stochSig[], ema[];
   ArraySetAsSeries(stochMain, true);
   ArraySetAsSeries(stochSig, true);
   ArraySetAsSeries(ema, true);
   if(CopyBuffer(hStoch, 0, 0, 5, stochMain) < 5) return;
   if(CopyBuffer(hEma, 0, 0, 5, ema) < 5) return;

   double close0 = iClose(Sym(), PERIOD_M1, 1); // last closed bar
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

   // Basket / solo management using market price
   if(count == 1)
   {
      // rely on broker TP set at entry; also protect with soft check
      double openPx = avgPrice;
      if(side==POSITION_TYPE_BUY && bid >= openPx + InpSoloTP) CloseAll();
      if(side==POSITION_TYPE_SELL && ask <= openPx - InpSoloTP) CloseAll();
   }
   else if(count >= 2)
   {
      if(side==POSITION_TYPE_BUY && bid >= avgPrice + InpBasketTP) CloseAll();
      if(side==POSITION_TYPE_SELL && ask <= avgPrice - InpBasketTP) CloseAll();
   }

   // refresh count after possible close
   count = CountPositions(side, avgPrice, lastPrice, lastTime);

   // Grid add
   if(count > 0 && count < InpMaxPositions)
   {
      if(side==POSITION_TYPE_BUY)
      {
         double adverse = lastPrice - ask;
         if(adverse >= InpGridStep)
            OpenTrade(ORDER_TYPE_BUY, 0); // basket managed by avg exit
      }
      else if(side==POSITION_TYPE_SELL)
      {
         double adverse = bid - lastPrice;
         if(adverse >= InpGridStep)
            OpenTrade(ORDER_TYPE_SELL, 0);
      }
      return; // do not reverse while in position
   }

   if(count > 0) return;
   if(!HourAllowed()) return;

   // Fresh entries on mean-reversion extremes
   if(st <= InpStochOS)
   {
      double stretch = em - close0;
      double against = -move3;
      if(stretch >= InpStretchMin && against >= InpMove3Min)
      {
         double tp = ask + InpSoloTP;
         OpenTrade(ORDER_TYPE_BUY, tp);
      }
   }
   else if(st >= InpStochOB)
   {
      double stretch = close0 - em;
      double against = move3;
      if(stretch >= InpStretchMin && against >= InpMove3Min)
      {
         double tp = bid - InpSoloTP;
         OpenTrade(ORDER_TYPE_SELL, tp);
      }
   }
}
