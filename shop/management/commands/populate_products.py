import os
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from shop.models import Category, Product


class Command(BaseCommand):
    help = 'Populate database with sample electronics data'

    def handle(self, *args, **options):
        # Clear existing data
        Product.objects.all().delete()
        Category.objects.all().delete()

        # Create categories
        smartphones = Category.objects.create(
            name='Смартфоны',
            description='Мобильные телефоны и аксессуары'
        )
        laptops = Category.objects.create(
            name='Ноутбуки',
            description='Портативные компьютеры для работы и развлечений'
        )
        tablets = Category.objects.create(
            name='Планшеты',
            description='Планшетные компьютеры и аксессуары'
        )
        accessories = Category.objects.create(
            name='Аксессуары',
            description='Кабели, зарядки, чехлы и другие аксессуары'
        )

        # Component categories
        cpu = Category.objects.create(
            name='Процессоры (CPU)',
            description='Процессоры Intel и AMD для персональных компьютеров'
        )
        gpu = Category.objects.create(
            name='Видеокарты (GPU)',
            description='Дискретные видеокарты NVIDIA и AMD'
        )
        ram = Category.objects.create(
            name='ОЗУ (RAM)',
            description='Модули оперативной памяти DDR4 и DDR5'
        )
        ssd = Category.objects.create(
            name='SSD диски',
            description='Твердотельные накопители NVMe и SATA'
        )
        psu = Category.objects.create(
            name='Блоки питания',
            description='Блоки питания различной мощности и типов'
        )
        cooling = Category.objects.create(
            name='Кулеры',
            description='Системы охлаждения для процессоров и корпусов'
        )
        monitors = Category.objects.create(
            name='Мониторы',
            description='Мониторы для программирования, творчества и игр'
        )
        motherboards = Category.objects.create(
            name='Материнские платы',
            description='Материнские платы различных форм-факторов'
        )

        # Get media path for images
        media_root = Path(os.getcwd()) / 'media' / 'products'

        # Create products
        products = [
            # Smartphones
            {
                'name': 'iPhone 15 Pro',
                'category': smartphones,
                'description': 'Флагманский смартфон Apple с процессором A17 Pro, камерой 48MP и дисплеем ProMotion 120Hz',
                'price': 119990,
                'stock': 15,
                'manufacturer': 'apple',
                'image_file': 'smartphone.svg'
            },
            {
                'name': 'Samsung Galaxy S24 Ultra',
                'category': smartphones,
                'description': 'Премиум Android смартфон с камерой 200MP, процессором Snapdragon 8 Gen 3 и 6.8" AMOLED дисплеем',
                'price': 124990,
                'stock': 12,
                'manufacturer': 'samsung',
                'image_file': 'smartphone.svg'
            },
            {
                'name': 'OnePlus 12',
                'category': smartphones,
                'description': 'Мощный смартфон с Snapdragon 8 Gen 3, быстрой зарядкой 100W и 6.7" AMOLED экраном',
                'price': 54990,
                'stock': 20,
                'manufacturer': 'other',
                'image_file': 'smartphone.svg'
            },

            # Laptops
            {
                'name': 'MacBook Pro 16" M3 Max',
                'category': laptops,
                'description': 'Профессиональный ноутбук с чипом M3 Max, 36GB памяти, 1TB SSD и 16" Mini-LED дисплеем',
                'price': 259990,
                'stock': 8,
                'manufacturer': 'apple',
                'image_file': 'laptop.svg'
            },
            {
                'name': 'ASUS ROG Zephyrus G16',
                'category': laptops,
                'description': 'Мощный игровой ноутбук с RTX 4090, Intel Core i9, 32GB RAM и 240Hz дисплеем',
                'price': 349990,
                'stock': 5,
                'manufacturer': 'other',
                'image_file': 'laptop.svg'
            },
            {
                'name': 'Lenovo ThinkPad X1 Carbon',
                'category': laptops,
                'description': 'Бизнес-ноутбук с Intel Core i7, 16GB RAM, 512GB SSD и долгой автономностью',
                'price': 149990,
                'stock': 14,
                'manufacturer': 'other',
                'image_file': 'laptop.svg'
            },

            # Tablets
            {
                'name': 'iPad Pro 12.9"',
                'category': tablets,
                'description': 'Мощный планшет с чипом M2, 256GB памяти, 12.9" Mini-LED и поддержкой Apple Pencil Pro',
                'price': 89990,
                'stock': 18,
                'manufacturer': 'apple',
                'image_file': ''
            },
            {
                'name': 'Samsung Galaxy Tab S9 Ultra',
                'category': tablets,
                'description': 'Премиум планшет с процессором Snapdragon 8 Gen 2, 14.6" AMOLED и S Pen в комплекте',
                'price': 79990,
                'stock': 10,
                'manufacturer': 'samsung',
                'image_file': ''
            },

            # Accessories
            {
                'name': 'Apple AirPods Pro (2nd gen)',
                'category': accessories,
                'description': 'Беспроводные наушники с активным шумоподавлением и адаптивным звуком',
                'price': 24990,
                'stock': 50,
                'manufacturer': 'apple',
                'image_file': 'headphones.svg'
            },
            {
                'name': 'Samsung 25W Super Fast Charger',
                'category': accessories,
                'description': 'Быстрая 25W зарядка для смартфонов и планшетов Samsung',
                'price': 4990,
                'stock': 100,
                'manufacturer': 'samsung',
                'image_file': ''
            },
            {
                'name': 'USB-C кабель Anker 3м',
                'category': accessories,
                'description': 'Прочный кабель USB-C с поддержкой быстрой зарядки и передачи данных',
                'price': 1290,
                'stock': 200,
                'manufacturer': 'other',
                'image_file': ''
            },

            # CPUs - Процессоры
            {
                'name': 'Intel Core i9-14900K',
                'category': cpu,
                'description': 'Флагманский процессор Intel последнего поколения с 24 ядрами и тактовой частотой до 6.2 ГГц',
                'price': 79990,
                'stock': 12,
                'manufacturer': 'other',
                'image_file': 'cpu.svg'
            },
            {
                'name': 'AMD Ryzen 9 7950X3D',
                'category': cpu,
                'description': 'Мощный процессор AMD с 16 ядрами, 3D V-Cache технологией и превосходной производительностью в играх',
                'price': 74990,
                'stock': 10,
                'manufacturer': 'other',
                'image_file': 'cpu.svg'
            },
            {
                'name': 'Intel Core i7-14700K',
                'category': cpu,
                'description': 'Универсальный процессор для работы и игр с 20 ядрами и хорошей производительностью',
                'price': 54990,
                'stock': 18,
                'manufacturer': 'other',
                'image_file': 'cpu.svg'
            },
            {
                'name': 'AMD Ryzen 5 7600X',
                'category': cpu,
                'description': 'Процессор среднего класса для офисных работ и легкого гейминга с 6 ядрами',
                'price': 24990,
                'stock': 25,
                'manufacturer': 'other',
                'image_file': 'cpu.svg'
            },

            # GPUs - Видеокарты
            {
                'name': 'NVIDIA RTX 4090',
                'category': gpu,
                'description': 'Флагманская видеокарта NVIDIA с 16384 ядрами для максимальной производительности',
                'price': 199990,
                'stock': 5,
                'manufacturer': 'other',
                'image_file': 'gpu.svg'
            },
            {
                'name': 'NVIDIA RTX 4080 Super',
                'category': gpu,
                'description': 'Мощная видеокарта для 4K гейминга и искусственного интеллекта',
                'price': 149990,
                'stock': 8,
                'manufacturer': 'other',
                'image_file': 'gpu.svg'
            },
            {
                'name': 'AMD Radeon RX 7900 XTX',
                'category': gpu,
                'description': 'Конкурентная видеокарта AMD с отличным соотношением цена/производительность',
                'price': 89990,
                'stock': 10,
                'manufacturer': 'other',
                'image_file': 'gpu.svg'
            },
            {
                'name': 'NVIDIA RTX 4070 Ti',
                'category': gpu,
                'description': 'Видеокарта среднего класса для игр в 1440p и 4K с хорошей производительностью',
                'price': 79990,
                'stock': 15,
                'manufacturer': 'other',
                'image_file': 'gpu.svg'
            },

            # RAM - Оперативная память
            {
                'name': 'Kingston Fury Beast DDR5 32GB',
                'category': ram,
                'description': 'Быстрая оперативная память DDR5 с частотой 6000 МГц для новых платформ',
                'price': 19990,
                'stock': 30,
                'manufacturer': 'other',
                'image_file': 'ram.svg'
            },
            {
                'name': 'Corsair Dominator Platinum DDR5 64GB',
                'category': ram,
                'description': 'Премиум набор оперативной памяти DDR5 64GB с подсветкой RGB',
                'price': 39990,
                'stock': 12,
                'manufacturer': 'other',
                'image_file': 'ram.svg'
            },
            {
                'name': 'G.Skill Trident Z5 DDR5 16GB',
                'category': ram,
                'description': 'Стабильная оперативная память DDR5 с частотой 5600 МГц',
                'price': 9990,
                'stock': 25,
                'manufacturer': 'other',
                'image_file': 'ram.svg'
            },
            {
                'name': 'Kingston HyperX Fury DDR4 16GB',
                'category': ram,
                'description': 'Надежная оперативная память DDR4 с хорошей совместимостью',
                'price': 6990,
                'stock': 40,
                'manufacturer': 'other',
                'image_file': 'ram.svg'
            },

            # SSD - Накопители
            {
                'name': 'Samsung 990 Pro 2TB',
                'category': ssd,
                'description': 'Высокопроизводительный NVMe SSD с скоростью до 7000 МБ/с',
                'price': 34990,
                'stock': 20,
                'manufacturer': 'samsung',
                'image_file': 'ssd.svg'
            },
            {
                'name': 'WD Black SN850X 1TB',
                'category': ssd,
                'description': 'Быстрый высокопроизводительный SSD для любителей и профессионалов',
                'price': 12990,
                'stock': 18,
                'manufacturer': 'other',
                'image_file': 'ssd.svg'
            },
            {
                'name': 'Crucial P5 Plus 500GB',
                'category': ssd,
                'description': 'Доступный NVMe SSD с хорошей производительностью',
                'price': 7990,
                'stock': 35,
                'manufacturer': 'other',
                'image_file': 'ssd.svg'
            },
            {
                'name': 'Kingston NV2 2TB',
                'category': ssd,
                'description': 'Надежный NVMe SSD с большой емкостью',
                'price': 19990,
                'stock': 15,
                'manufacturer': 'other',
                'image_file': 'ssd.svg'
            },

            # PSU - Блоки питания
            {
                'name': 'Corsair HX850 Platinum',
                'category': psu,
                'description': 'Премиум модульный блок питания 850W с эффективностью 80+ Platinum',
                'price': 14990,
                'stock': 16,
                'manufacturer': 'other',
                'image_file': 'psu.svg'
            },
            {
                'name': 'EVGA SuperNOVA GT 1000W',
                'category': psu,
                'description': 'Мощный модульный блок питания 1000W для максимальных конфигураций',
                'price': 19990,
                'stock': 8,
                'manufacturer': 'other',
                'image_file': 'psu.svg'
            },
            {
                'name': 'Seasonic Focus Plus 750W',
                'category': psu,
                'description': 'Тихий и эффективный блок питания 750W для среднего класса',
                'price': 9990,
                'stock': 22,
                'manufacturer': 'other',
                'image_file': 'psu.svg'
            },
            {
                'name': 'Thermaltake Toughpower 650W',
                'category': psu,
                'description': 'Надежный блок питания 650W для офисных и игровых систем',
                'price': 7490,
                'stock': 30,
                'manufacturer': 'other',
                'image_file': 'psu.svg'
            },

            # CPU Coolers - Кулеры
            {
                'name': 'Noctua NH-D15 Chromax',
                'category': cooling,
                'description': 'Премиум воздушный кулер с двумя вентиляторами и низким уровнем шума',
                'price': 11990,
                'stock': 14,
                'manufacturer': 'other',
                'image_file': 'cpu_cooler.svg'
            },
            {
                'name': 'CORSAIR H150i Elite Capellix',
                'category': cooling,
                'description': 'Жидкостное охлаждение AIO 360mm с тремя вентиляторами и RGB',
                'price': 19990,
                'stock': 10,
                'manufacturer': 'other',
                'image_file': 'cpu_cooler.svg'
            },
            {
                'name': 'Be quiet! Dark Rock Pro 4',
                'category': cooling,
                'description': 'Мощный воздушный кулер с 7 тепловыми трубками для интенсивного охлаждения',
                'price': 9990,
                'stock': 18,
                'manufacturer': 'other',
                'image_file': 'cpu_cooler.svg'
            },
            {
                'name': 'Arctic Freezer 50 TR',
                'category': cooling,
                'description': 'Универсальный кулер для процессоров Ryzen с 2 вентиляторами',
                'price': 5990,
                'stock': 28,
                'manufacturer': 'other',
                'image_file': 'cpu_cooler.svg'
            },

            # Monitors - Мониторы
            {
                'name': 'Samsung M7 Smart Monitor 32"',
                'category': monitors,
                'description': 'Умный монитор 32" с подключением к интернету и встроенными приложениями',
                'price': 59990,
                'stock': 7,
                'manufacturer': 'samsung',
                'image_file': 'monitor.svg'
            },
            {
                'name': 'LG UltraWide 34" 21:9',
                'category': monitors,
                'description': 'Ультраширокий монитор для многозадачности с разрешением 3440x1440',
                'price': 79990,
                'stock': 5,
                'manufacturer': 'other',
                'image_file': 'monitor.svg'
            },
            {
                'name': 'ASUS ProArt PA278QV',
                'category': monitors,
                'description': 'Профессиональный монитор 27" для дизайна и цветокоррекции с 100% sRGB',
                'price': 34990,
                'stock': 9,
                'manufacturer': 'other',
                'image_file': 'monitor.svg'
            },
            {
                'name': 'MSI Optix G273QF 27"',
                'category': monitors,
                'description': 'Игровой монитор 27" с частотой 240Hz и временем отклика 1ms',
                'price': 29990,
                'stock': 12,
                'manufacturer': 'other',
                'image_file': 'monitor.svg'
            },

            # Motherboards - Материнские платы
            {
                'name': 'ASUS ROG Maximus Z890-E',
                'category': motherboards,
                'description': 'Премиум материнская плата Z890 для Intel Core Ultra Extreme',
                'price': 44990,
                'stock': 8,
                'manufacturer': 'other',
                'image_file': 'motherboard.svg'
            },
            {
                'name': 'MSI MEG X870E-E',
                'category': motherboards,
                'description': 'Флагманская материнская плата X870E для AMD Ryzen 9 7000',
                'price': 54990,
                'stock': 6,
                'manufacturer': 'other',
                'image_file': 'motherboard.svg'
            },
            {
                'name': 'Gigabyte B850 AORUS Master',
                'category': motherboards,
                'description': 'Высокопроизводительная материнская плата B850 с мощной системой питания',
                'price': 29990,
                'stock': 14,
                'manufacturer': 'other',
                'image_file': 'motherboard.svg'
            },
            {
                'name': 'MSI PRO B850-PLUS',
                'category': motherboards,
                'description': 'Надежная материнская плата B850 для работы и игр',
                'price': 18990,
                'stock': 20,
                'manufacturer': 'other',
                'image_file': 'motherboard.svg'
            },

            # Cables - Кабели
            {
                'name': 'Модульные кабели Corsair',
                'category': accessories,
                'description': 'Набор модульных кабелей для блоков питания Corsair 850W',
                'price': 3990,
                'stock': 50,
                'manufacturer': 'other',
                'image_file': 'cables.svg'
            },
            {
                'name': 'HDMI 2.1 кабель 3М',
                'category': accessories,
                'description': 'Высокоскоростной HDMI 2.1 кабель для 8K видео',
                'price': 2990,
                'stock': 80,
                'manufacturer': 'other',
                'image_file': ''
            },
            {
                'name': 'DisplayPort 1.4 кабель 2М',
                'category': accessories,
                'description': '8K DisplayPort с улучшенной передачей сигнала',
                'price': 2490,
                'stock': 60,
                'manufacturer': 'other',
                'image_file': ''
            },
        ]

        for product_data in products:
            image_file = product_data.pop('image_file', '')
            product = Product.objects.create(**product_data)

            # Try to attach image if file exists
            if image_file:
                image_path = media_root / image_file
                if image_path.exists():
                    with open(image_path, 'rb') as f:
                        product.image.save(f"{product.slug}.svg", File(f), save=True)
                    self.stdout.write(f'  ✓ Добавлена картинка для {product.name}')

        self.stdout.write(
            self.style.SUCCESS('✓ База данных успешно заполнена примерами товаров!')
        )
        self.stdout.write(f'Создано {len(products)} товаров и 11 категорий')
