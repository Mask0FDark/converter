import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import json
import os
import requests
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class CurrencyConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Обменник валют")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # API ключи
        self.API_KEY = "Ваш API ключ"#Ваш API ключ
        self.COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether,solana,dogecoin&vs_currencies=usd"
        
        # Файлы для хранения данных
        self.history_file = "exchange_history.json"
        self.rates_file = "exchange_rates.json"
        
        # Загрузка курсов валют
        self.rates = self.load_rates()
        
        # История операций
        self.history = []
        self.load_history()
        
        # Создание вкладок
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Создаем вкладки
        self.create_exchange_tab()
        self.create_history_tab()
        self.create_chart_tab()
        
        # Статус бар
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Обновляем статус
        self.update_status()
        
        # Запускаем обновление курсов
        self.update_rates()
        self.schedule_rate_updates()
    
    def load_rates(self):
        """Загрузка курсов валют из файла или API"""
        rates = {
            'USD': 1.0,
            'EUR': 0.93,
            'RUB': 92.5,
            'KZT': 462.5,
            'GBP': 0.79,
            'CNY': 7.25
        }
        
        # Добавляем криптовалюты с базовыми значениями
        crypto_rates = {
            'BTC': 50000.0,
            'ETH': 3000.0,
            'USDT': 1.0,
            'SOL': 100.0,
            'DOGE': 0.15
        }
        rates.update(crypto_rates)
        
        # Пытаемся загрузить из файла
        if os.path.exists(self.rates_file):
            try:
                with open(self.rates_file, 'r', encoding='utf-8') as f:
                    saved_rates = json.load(f)
                    # Обновляем только существующие ключи
                    for key in rates:
                        if key in saved_rates:
                            rates[key] = saved_rates[key]
            except:
                pass
        
        return rates
    
    def save_rates(self):
        """Сохранение курсов валют в файл"""
        try:
            with open(self.rates_file, 'w', encoding='utf-8') as f:
                json.dump(self.rates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_error(f"Не удалось сохранить курсы валют: {str(e)}")
    
    def update_rates(self):
        """Обновление курсов валют через API"""
        try:
            # Обновляем фиатные валюты
            base_currency = "USD"
            for currency in self.rates:
                if currency == base_currency or currency in ['BTC', 'ETH', 'USDT', 'SOL', 'DOGE']:
                    continue
                
                rate = self.get_exchange_rate(base_currency, currency)
                if isinstance(rate, float):
                    self.rates[currency] = rate
            
            # Обновляем криптовалюты
            response = requests.get(self.COINGECKO_URL)
            if response.status_code == 200:
                data = response.json()
                self.rates['BTC'] = data['bitcoin']['usd']
                self.rates['ETH'] = data['ethereum']['usd']
                self.rates['USDT'] = data['tether']['usd']
                self.rates['SOL'] = data['solana']['usd']
                self.rates['DOGE'] = data['dogecoin']['usd']
            
            self.save_rates()
            self.last_update = datetime.now()
            self.update_status()
            return True
        except Exception as e:
            self.log_error(f"Ошибка при обновлении курсов: {str(e)}")
            return False
    
    def get_exchange_rate(self, base_currency, target_currency):
        """Получение курса валюты через API"""
        try:
            url = f"https://v6.exchangerate-api.com/v6/{self.API_KEY}/pair/{base_currency}/{target_currency}"
            response = requests.get(url)
            data = response.json()
            if data['result'] == "success":
                return data['conversion_rate']
            return None
        except Exception as e:
            self.log_error(f"Ошибка при получении курса {base_currency}/{target_currency}: {str(e)}")
            return None
    
    def schedule_rate_updates(self):
        """Запланировать регулярное обновление курсов"""
        if self.update_rates():
            self.status_var.set("Курсы успешно обновлены")
        else:
            self.status_var.set("Ошибка при обновлении курсов")
        
        # Запускаем обновление каждые 10 минут
        self.root.after(600000, self.schedule_rate_updates)
    
    def load_history(self):
        """Загрузка истории операций из файла JSON"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except:
                self.history = []
    
    def save_history(self):
        """Сохранение истории операций в файл JSON"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_error(f"Не удалось сохранить историю: {str(e)}")
    
    def update_status(self):
        """Обновление статус бара"""
        if hasattr(self, 'last_update'):
            status = f"Последнее обновление: {self.last_update.strftime('%d.%m.%Y %H:%M')} | "
        else:
            status = "Курсы еще не обновлены | "
        
        status += f"BTC: ${self.rates['BTC']:.2f} | ETH: ${self.rates['ETH']:.2f}"
        self.status_var.set(status)
    
    def create_exchange_tab(self):
        """Создание вкладки для обмена валют"""
        exchange_frame = ttk.Frame(self.notebook)
        self.notebook.add(exchange_frame, text="Обмен валют")
        
        # Стиль для виджетов
        style = ttk.Style()
        style.configure("Exchange.TLabel", font=("Arial", 10))
        style.configure("Exchange.TButton", font=("Arial", 10))
        
        # Заголовок
        ttk.Label(
            exchange_frame, 
            text="Конвертер валют", 
            font=("Arial", 14, "bold")
        ).pack(pady=10)
        
        # Фрейм для полей ввода
        input_frame = ttk.Frame(exchange_frame)
        input_frame.pack(pady=10, fill=tk.X, padx=20)
        
        # Поле ввода суммы
        ttk.Label(input_frame, text="Сумма:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.amount_entry = ttk.Entry(input_frame, width=20)
        self.amount_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.amount_entry.focus()
        
        # Выбор исходной валюты
        ttk.Label(input_frame, text="Из валюты:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.from_currency = ttk.Combobox(input_frame, values=list(self.rates.keys()), width=17)
        self.from_currency.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        self.from_currency.current(0)
        
        # Выбор целевой валюты
        ttk.Label(input_frame, text="В валюту:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.to_currency = ttk.Combobox(input_frame, values=list(self.rates.keys()), width=17)
        self.to_currency.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        self.to_currency.current(1)
        
        # Кнопки
        button_frame = ttk.Frame(exchange_frame)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame, 
            text="Конвертировать", 
            command=self.convert
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, 
            text="↔ Поменять валюты", 
            command=self.swap_currencies
        ).pack(side=tk.LEFT, padx=5)
        
        # Поле результата
        result_frame = ttk.Frame(exchange_frame)
        result_frame.pack(pady=10, fill=tk.X, padx=20)
        
        ttk.Label(result_frame, text="Результат:").grid(row=0, column=0, sticky=tk.W)
        self.result_var = tk.StringVar()
        result_entry = ttk.Entry(
            result_frame, 
            textvariable=self.result_var, 
            state="readonly",
            width=25,
            font=("Arial", 10, "bold"),
            foreground="blue"
        )
        result_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        
        # Кнопка отправки на почту
        ttk.Button(
            result_frame, 
            text="Отправить результат на почту", 
            command=self.send_email
        ).grid(row=1, column=0, columnspan=2, pady=10)
        
        # Настройка веса столбцов для центрирования
        input_frame.columnconfigure(0, weight=1)
        input_frame.columnconfigure(1, weight=2)
        result_frame.columnconfigure(0, weight=1)
        result_frame.columnconfigure(1, weight=2)
    
    def create_history_tab(self):
        """Создание вкладки истории операций"""
        history_frame = ttk.Frame(self.notebook)
        self.notebook.add(history_frame, text="История операций")
        
        # Заголовок
        ttk.Label(
            history_frame, 
            text="История конвертаций", 
            font=("Arial", 14, "bold")
        ).pack(pady=10)
        
        # Кнопки управления историей
        history_controls = ttk.Frame(history_frame)
        history_controls.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            history_controls, 
            text="Очистить историю", 
            command=self.clear_history
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            history_controls, 
            text="Обновить", 
            command=self.update_history_table
        ).pack(side=tk.LEFT, padx=5)
        
        # Таблица истории
        columns = ("#1", "#2", "#3", "#4", "#5", "#6")
        self.history_tree = ttk.Treeview(
            history_frame, 
            columns=columns, 
            show="headings",
            height=15
        )
        
        # Настройка столбцов
        self.history_tree.heading("#1", text="Дата и время")
        self.history_tree.heading("#2", text="Сумма")
        self.history_tree.heading("#3", text="Из валюты")
        self.history_tree.heading("#4", text="В валюту")
        self.history_tree.heading("#5", text="Результат")
        self.history_tree.heading("#6", text="Курс")
        
        self.history_tree.column("#1", width=150, anchor=tk.CENTER)
        self.history_tree.column("#2", width=100, anchor=tk.CENTER)
        self.history_tree.column("#3", width=80, anchor=tk.CENTER)
        self.history_tree.column("#4", width=80, anchor=tk.CENTER)
        self.history_tree.column("#5", width=120, anchor=tk.CENTER)
        self.history_tree.column("#6", width=100, anchor=tk.CENTER)
        
        # Добавление скроллбара
        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscroll=scrollbar.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Инициализация таблицы истории
        self.update_history_table()
    
    def create_chart_tab(self):
        """Создание вкладки с графиком курсов"""
        chart_frame = ttk.Frame(self.notebook)
        self.notebook.add(chart_frame, text="График курсов")
        
        # Заголовок
        ttk.Label(
            chart_frame, 
            text="Динамика курса криптовалют к USD", 
            font=("Arial", 14, "bold")
        ).pack(pady=10)
        
        # Выбор валюты для графика
        currency_frame = ttk.Frame(chart_frame)
        currency_frame.pack(pady=5)
        
        ttk.Label(currency_frame, text="Выберите криптовалюту:").pack(side=tk.LEFT, padx=5)
        self.chart_currency = ttk.Combobox(
            currency_frame, 
            values=['BTC', 'ETH', 'SOL', 'DOGE'],
            width=8
        )
        self.chart_currency.pack(side=tk.LEFT, padx=5)
        self.chart_currency.current(0)
        
        # Фрейм для графика
        graph_frame = ttk.Frame(chart_frame)
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Создаем фигуру для matplotlib
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Кнопки для выбора периода
        period_frame = ttk.Frame(chart_frame)
        period_frame.pack(pady=10)
        
        ttk.Button(
            period_frame, 
            text="Показать за неделю", 
            command=lambda: self.update_chart(7)
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            period_frame, 
            text="Показать за месяц", 
            command=lambda: self.update_chart(30)
        ).pack(side=tk.LEFT, padx=5)
        
        # Инициализируем график
        self.update_chart(7)
    
    def update_chart(self, days):
        """Обновление графика курсов криптовалют к USD"""
        # Получаем выбранную криптовалюту
        currency = self.chart_currency.get()
        if not currency:
            currency = 'BTC'  # Значение по умолчанию
        
        # Соответствие символов криптовалют их ID в CoinGecko
        coin_ids = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'SOL': 'solana',
            'DOGE': 'dogecoin'
        }
        
        coin_id = coin_ids.get(currency)
        if not coin_id:
            messagebox.showerror("Ошибка", "Выбрана неподдерживаемая криптовалюта")
            return
        
        try:
            # Получаем исторические данные
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Извлекаем цены и даты
            prices = data['prices']
            dates = [datetime.fromtimestamp(price[0]/1000) for price in prices]
            values = [price[1] for price in prices]
            
            # Очищаем предыдущий график
            self.ax.clear()
            
            # Строим новый график
            date_labels = [d.strftime('%d.%m') for d in dates]
            self.ax.plot(date_labels, values, 'o-', label=f'{currency}/USD')
            
            # Настраиваем внешний вид
            self.ax.set_title(f'Динамика курса {currency}/USD за {days} дней')
            self.ax.set_xlabel('Дата')
            self.ax.set_ylabel(f'Цена в USD')
            self.ax.legend()
            self.ax.grid(True, linestyle='--', alpha=0.7)
            
            # Поворачиваем подписи дат для лучшей читаемости
            plt.setp(self.ax.get_xticklabels(), rotation=45, ha='right')
            
            # Обновляем холст
            self.canvas.draw()
            
        except Exception as e:
            self.log_error(f"Ошибка при получении данных для графика: {str(e)}")
            messagebox.showerror("Ошибка", "Не удалось получить данные для графика")
    
    def convert(self):
        """Выполнение конвертации валюты"""
        try:
            amount = float(self.amount_entry.get())
            from_curr = self.from_currency.get()
            to_curr = self.to_currency.get()
            
            # Конвертация через USD как базовую валюту
            if from_curr == to_curr:
                result = amount
                rate = 1.0
            else:
                # Конвертация: исходная валюта -> USD -> целевая валюта
                usd_amount = amount / self.rates[from_curr]
                result = usd_amount * self.rates[to_curr]
                rate = self.rates[to_curr] / self.rates[from_curr]
            
            # Форматируем результат
            result_str = f"{result:.2f} {to_curr}"
            self.result_var.set(result_str)
            
            # Сохраняем в историю
            operation = {
                'datetime': datetime.now().strftime("%d.%m.%Y %H:%M"),
                'amount': f"{amount:.2f} {from_curr}",
                'from_curr': from_curr,
                'to_curr': to_curr,
                'result': result_str,
                'rate': f"{rate:.4f}"
            }
            self.history.append(operation)
            self.save_history()  # Сохраняем историю в файл
            self.update_history_table()
            
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректную сумму")
        except KeyError:
            messagebox.showerror("Ошибка", "Выберите валюту из списка")
        except Exception as e:
            self.log_error(f"Ошибка при конвертации: {str(e)}")
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
    
    def update_history_table(self):
        """Обновление таблицы истории операций"""
        # Очищаем существующие записи
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # Добавляем новые записи в обратном порядке (последние операции сверху)
        for op in reversed(self.history[-50:]):
            self.history_tree.insert("", tk.END, values=(
                op['datetime'],
                op['amount'],
                op['from_curr'],
                op['to_curr'],
                op['result'],
                op['rate']
            ))
    
    def clear_history(self):
        """Очистка истории операций"""
        if messagebox.askyesno("Подтверждение", "Вы действительно хотите очистить историю операций?"):
            self.history = []
            self.save_history()
            self.update_history_table()
    
    def swap_currencies(self):
        """Меняем выбранные валюты местами"""
        current_from = self.from_currency.current()
        current_to = self.to_currency.current()
        self.from_currency.current(current_to)
        self.to_currency.current(current_from)
        self.convert()
    
    def log_error(self, error_message):
        """Логирование ошибки и отправка уведомления"""
        print(f"[ОШИБКА] {error_message}")
        self.send_error_email(error_message)
    
    def send_error_email(self, error_message):
        """Отправка уведомления об ошибке на почту"""
        try:
            # Конфигурация почты (замените на свои данные)
            smtp_server = "smtp.yandex.ru"
            smtp_port = 587
            sender_email = "your_email@yandex.ru"
            sender_password = "your_password"
            receiver_email = "admin@example.com"
            
            # Создание сообщения
            message = MIMEMultipart()
            message["From"] = sender_email
            message["To"] = receiver_email
            message["Subject"] = "Ошибка в приложении Обменник валют"
            
            body = f"""
            Произошла ошибка в приложении:
            {error_message}
            
            Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            message.attach(MIMEText(body, "plain"))
            
            # Отправка сообщения
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(message)
            
            print("Уведомление об ошибке отправлено")
        except Exception as e:
            print(f"Не удалось отправить уведомление об ошибке: {str(e)}")
    
    def send_email(self):
        """Отправка результата конвертации на почту"""
        result = self.result_var.get()
        if result:
            try:
                # Конфигурация почты (замените на свои данные)
                smtp_server = "smtp.yandex.ru"
                smtp_port = 587
                sender_email = "your_email@yandex.ru"
                sender_password = "your_password"
                
                # Диалоговое окно для ввода email получателя
                email_dialog = tk.Toplevel(self.root)
                email_dialog.title("Отправка результата")
                email_dialog.geometry("400x200")
                email_dialog.resizable(False, False)
                
                ttk.Label(email_dialog, text="Введите email получателя:").pack(pady=10)
                
                email_var = tk.StringVar()
                email_entry = ttk.Entry(email_dialog, textvariable=email_var, width=30)
                email_entry.pack(pady=5)
                email_entry.focus()
                
                status_var = tk.StringVar()
                status_label = ttk.Label(email_dialog, textvariable=status_var)
                status_label.pack(pady=5)
                
                def send():
                    receiver_email = email_var.get()
                    if not receiver_email or "@" not in receiver_email:
                        status_var.set("Некорректный email")
                        return
                    
                    try:
                        # Создание сообщения
                        message = MIMEMultipart()
                        message["From"] = sender_email
                        message["To"] = receiver_email
                        message["Subject"] = "Результат конвертации валют"
                        
                        body = f"""
                        Результат конвертации:
                        {result}
                        
                        Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}
                        """
                        message.attach(MIMEText(body, "plain"))
                        
                        # Отправка сообщения
                        with smtplib.SMTP(smtp_server, smtp_port) as server:
                            server.starttls()
                            server.login(sender_email, sender_password)
                            server.send_message(message)
                        
                        status_var.set("Сообщение успешно отправлено!")
                        email_dialog.after(2000, email_dialog.destroy)
                    except Exception as e:
                        status_var.set(f"Ошибка отправки: {str(e)}")
                
                ttk.Button(email_dialog, text="Отправить", command=send).pack(pady=10)
                
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось отправить email: {str(e)}")
        else:
            messagebox.showwarning("Ошибка", "Сначала выполните конвертацию")

if __name__ == "__main__":
    root = tk.Tk()
    app = CurrencyConverterApp(root)
    root.mainloop()
