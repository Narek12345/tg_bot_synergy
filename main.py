import io
import os
import json
import base64
import secrets
import requests
from PIL import Image
from io import BytesIO

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram import executor

from config import (
	TELEGRAM_TOKEN,
	folder_id,
	oauth_token
)

VISION_URL = 'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze'
URL = 'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize'
URI_INFO = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id='
URI = f'https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/'

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)


def save_pdf_from_bytesio(pdf_bytesio, file_path):
	# Получаем байты из объекта BytesIO
	pdf_bytes = pdf_bytesio.getvalue()
	# Записываем байты в файл
	with open(file_path, 'wb') as f:
		f.write(pdf_bytes)


def create_token(oauth_token):
  params = {'yandexPassportOauthToken': oauth_token}
  response = requests.post('https://iam.api.cloud.yandex.net/iam/v1/tokens', params=params)                                                   
  decode_response = response.content.decode('UTF-8')
  text = json.loads(decode_response)
  iam_token = text.get('iamToken')

  return iam_token


@dp.message_handler(commands="start")
async def start_cmd(message: Message):
	await message.reply("Привет! Отправь мне PDF или изображение с текстом для распознавания.")


async def image_recognition(file, type_file):
	"""Получаем файл изображения, отправляем его в Yandex Cloud для распознавания текста и возвращаем весь распознанный текст."""
	iam_token = create_token(oauth_token)

	if type_file == 'Image':	
		with open(file, 'rb') as f:
			image_data = f.read()
	
		headers = {
			'Authorization': f'Bearer {iam_token}',
			'Content-Type': 'application/json'
		}
	
		# Подготовка данных изображения.
		encoded_image = base64.b64encode(image_data).decode('UTF-8')
	
		# Подготовка данных для запроса
		payload = {
			"folderId": folder_id,
			"analyze_specs": [{
				"content": encoded_image,
				"features": [{
					"type": "TEXT_DETECTION",
					"text_detection_config": {"language_codes": ["ru", "en"]}
				}]
			}]
		}
	
		response = requests.post(VISION_URL, headers=headers, json=payload)
		decode_resp = response.content.decode('UTF-8')
		result = json.loads(decode_resp)
	
		
		# Извлечение и объединение всего текста из ответа
		recognized_text = []
		try:
			for result in result['results'][0]['results']:
				if 'textDetection' in result:
					for page in result['textDetection']['pages']:
						for block in page['blocks']:
							for line in block['lines']:
								line_text = ' '.join([word['text'] for word in line['words']])
								recognized_text.append(line_text)
			return {"recognized_text": ' '.join(recognized_text)}
		except (IndexError, KeyError):
			return {"error": "Текст не был распознан или не найден в изображении."}

	elif type_file == 'Document':
		with open(file, 'rb') as f:
			pdf_data = f.read()

		headers = {
			'Authorization': f'Bearer {iam_token}',
			'Content-Type': 'application/json'
		}

		# Подготовка данных изображения.
		encoded_pdf = base64.b64encode(pdf_data).decode('UTF-8')

		body = {
			"mimeType": "application/pdf",
			"languageCodes": ["*"],
			"model": "page",
			"content": encoded_pdf
		}

		response = requests.post(VISION_URL, headers=headers, data=encoded_pdf)
		print(response, '\n\n\n')


@dp.message_handler(content_types=['photo'])
async def process_img(message: Message):
	await message.answer('Изображение обрабатывается !')

	try:
		file_id = message.photo[3].file_id
	except:
		try:
			file_id = message.photo[2].file_id
		except:
			try:
				file_id = message.photo[1].file_id
			except:
				try:
					file_id = message.photo[0].file_id
				except:
					pass

	resp = requests.get(URI_INFO + file_id)
	img_path = resp.json()['result']['file_path']
	img = requests.get(URI + img_path)

	# Открываем файн.
	img = Image.open(BytesIO(img.content))

	# Сохраняем файл.
	img_name = secrets.token_hex(8)
	path_to_img = f'images/{img_name}.png'
	img.save(path_to_img, format='PNG')

	answer = await image_recognition(path_to_img, 'Image')

	await message.answer(text=answer['recognized_text'])

	# Удаляем картинку.
	os.remove(path_to_img)


@dp.message_handler(content_types=['document'])
async def process_doc(message: Message):
	await message.answer('Документ обрабатывается !')

	# Получаем информацию о документе PDF
	file_id = message.document.file_id
	file_info = await bot.get_file(file_id)
	file_path = file_info.file_path

	# Скачиваем документ
	file_data = await bot.download_file(file_path)

	file_name = secrets.token_hex(8) + '.pdf'
	file_path = f'documents/{file_name}'

	saved_file_path = save_pdf_from_bytesio(file_data, file_path)

	answer = await image_recognition(file_path, 'Document')

	await message.answer(text=answer)

	# Удаляем картинку.
	os.remove(f'documents/{file_name}')


if __name__ == '__main__':
	executor.start_polling(dp, skip_updates=True)