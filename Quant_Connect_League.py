#region imports
from AlgorithmImports import *
#endregion

class DiversifiedTradingStrategy(QCAlgorithm):

    def Initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 6, 30)
        self.set_cash(1000000)
        
        self.positionSizePercent = 0.5  # Allocate 25% to each class
        self.momentum_entry = 60
        self.oversold_entry = 30
        self.momentum_exit = 40
        self.overbought_exit = 70
        self.minimumVolume = 50000
        self.margin_safety = 0.05
        self.min_trade_value = 1000

        # Define universes
        #self.crypto_universe = ['BTCUSD', 'LTCUSD', 'ETHUSD', 'ETCUSD', 'RRTUSD', 'ZECUSD', 'XMRUSD', 'XRPUSD', 'EOSUSD', 
        #            'SANUSD', 'OMGUSD', 'NEOUSD', 'ETPUSD', 'BTGUSD', 'SNTUSD', 'BATUSD', 'FUNUSD', 'ZRXUSD', 
        #            'TRXUSD', 'REQUSD', 'LRCUSD', 'WAXUSD', 'DAIUSD', 'BFTUSD', 'ODEUSD', 'ANTUSD', 'XLMUSD', 
        #            'XVGUSD', 'MKRUSD', 'KNCUSD', 'LYMUSD', 'UTKUSD', 'VEEUSD', 'ESSUSD', 'IQXUSD', 'ZILUSD', 
        #            'BNTUSD', 'XRAUSD', 'VETUSD', 'GOTUSD', 'XTZUSD', 'MLNUSD', 'PNKUSD', 'DGBUSD', 'BSVUSD', 
        #            'ENJUSD', 'PAXUSD']
        self.crypto_universe = [
            'BTCUSD',
            'ETHUSD',
            'XRPUSD',
            'LTCUSD',
            'BNBUSD',
            'TRXUSD',
            'XLMUSD'
        ]

        self.stock_universe = [
            'AAPL',
            'NVDA',
            'TSLA',
            'GOOG',
            'SOFI',
            'COIN',
            'OXY',
            'META'
        ]

        #self.stock_universe = ['AAPL', 'MSFT', 'GOOG', "TSLA", "NVDA", "META", "COIN", "GOOG", "SAVA", "OXY", "CHGG", "AMD",
         #           "PALAF", "SOFI", "AWZN", "AZO", "CHWY", "ETSY", "MGM", "JPM", "MA", "XOM", "BKR",
          #          "NEE", "IART", "HEI", "HWM", "SBGSF", "ECL", "NFLX", "TSN", "VST", "CEG", "PLNT",
           #         "CRM", "NOW"]
        #self.index_universe = ['DODFX', 'ACMVX', 'PRFHX', 'VOOG', 'SCHG', 'VGT', 'SCHD', 'SDY', 'VYM', 'FCNTX', 'AGTHX',
        #            'TRBCX', 'VTWAX', 'VCLT', 'VEXAX', 'FTIHX', 'VBR', 'FSENX', 'FSPCX', 'FMILX']
        
        self.pairs = []
        self.AddUniverse(self.crypto_universe, self.add_crypto, "Crypto")
        self.AddUniverse(self.stock_universe, self.add_equity, "Stock")
        #self.AddUniverse(self.index_universe, self.add_equity, "Index")

        self.set_benchmark(self.add_equity('SPY').Symbol)
        self.set_warmup(30)
        self.debug("Initialization complete")

    def AddUniverse(self, universe, addMethod, universeName):
        for ticker in universe:
            try:
                pair = Pair(self, addMethod(ticker).Symbol, self.minimumVolume, universeName)
                self.pairs.append(pair)
                self.debug(f"Added {ticker} to {universeName} universe")
            except Exception as e:
                self.debug(f"Failed to add {ticker} to {universeName} universe: {str(e)}")

    def on_data(self, data):
        if self.is_warming_up:
            return

        allocation_per_class = self.portfolio.total_portfolio_value * self.positionSizePercent

        # Track allocation by asset class
        class_allocations = {"Crypto": 0.0, "Stock": 0.0}

        for pair in self.pairs:
            if not pair.rsi.IsReady or not pair.Investable():
                continue

            symbol = pair.symbol
            rsi = pair.rsi.Current.Value
            universe_name = pair.universe_name

            rsi_decreasing = pair.previous_rsi is not None and rsi < pair.previous_rsi
            rsi_increasing = pair.previous_rsi is not None and rsi > pair.previous_rsi
            pair.previous_rsi = rsi

            # Liquidation logic
            if self.portfolio[symbol].invested:
                if rsi > self.overbought_exit and rsi_increasing:
                    self.liquidate(symbol)
                elif rsi < self.momentum_exit and rsi_decreasing:
                    self.liquidate(symbol)

            if pair.higher_high:

                # Buying logic
                if (class_allocations[universe_name] < allocation_per_class) and (self.portfolio.margin_remaining > 0.5 * allocation_per_class):
                    if (rsi_increasing and rsi > self.momentum_entry and rsi < self.overbought_exit) or (rsi_decreasing and rsi < self.oversold_entry):
                        allocation = allocation_per_class - class_allocations[universe_name]
                        
                        if allocation > self.margin_safety * self.portfolio.margin_remaining:
                            allocation = self.portfolio.margin_remaining

                        usable_allocation = min(
                            allocation_per_class - class_allocations[universe_name],
                            self.portfolio.margin_remaining * self.margin_safety
                        )

                        percentage = usable_allocation / self.portfolio.total_portfolio_value
                        quantity = self.calculate_order_quantity(symbol, percentage)

                        if quantity != 0:
                            estimated_value = abs(quantity) * self.securities[symbol].price
                            if estimated_value >= self.min_trade_value:
                                try:
                                    self.market_order(symbol, quantity)
                                    class_allocations[universe_name] += estimated_value
                                except Exception as e:
                                    self.debug(f"Failed to buy {symbol}: {e}")
                                    self.debug(f"Margin Remaining: {self.portfolio.margin_remaining}")
                                    self.debug(f"Cash Remaining: {self.portfolio.cash}")



class Pair:
    def __init__(self, algorithm, symbol, minimumVolume, universe_name=None):
        self.algorithm = algorithm
        self.symbol = symbol
        self.universe_name = universe_name
        self.minimumVolume = minimumVolume

        # Inficators
        self.rsi = algorithm.RSI(self.symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
        self.volume = algorithm.SMA(self.symbol, 30, Resolution.DAILY, Field.VOLUME)
        #self.ema = algorithm.EMA(self.symbol, 200, Resolution.DAILY, Field.VOLUME)
        #self.vwap = algorithm.VWAP(self.symbol, 30 , Resolution.DAILY, Field.VOLUME)
        #self.macd = algorithm.MACD(self.symbol, 30, Resolution.DAILY, Field.VOLUME)
        
        self.previous_rsi = None

        # Biweekly consolidator setup
        self.biweekly_consolidator = TradeBarConsolidator(timedelta(days=14))
        algorithm.SubscriptionManager.AddConsolidator(self.symbol, self.biweekly_consolidator)
        self.biweekly_consolidator.data_consolidated += self.OnBiweeklyBar
        self.current_biweek = {"high": None, "low" : None}
        self.previous_biweek = {"high": None, "low" : None}
        self.higher_high = False
        self.lower_low = False
    
    def OnBiweeklyBar(self, sender, bar):
        # Check for valid high prices
        if bar.High is not None and bar.Low is not None:
            self.previous_biweek = self.current_biweek.copy()
            self.current_biweek["high"] = bar.High
            self.current_biweek["low"] = bar.Low

        # Check for higher highs
        if self.previous_biweek["high"] is not None:
            self.higher_high = self.current_biweek["high"] > self.previous_biweek["high"]
            self.lower_low = self.current_biweek["low"] < self.previous_biweek["low"]
            
    def Investable(self):
        # Ensure indicators are ready
        if not self.volume.IsReady or not self.rsi.IsReady:
            return False
        return self.volume.Current.Value > self.minimumVolume
