@echo off
rem Copia questo file come imposta_credenziali_telegram.bat, inserisci i tuoi valori
rem e lancialo una volta. Il file con i valori veri e' escluso da git (.gitignore).
setx TELEGRAM_TOKEN_CHAMPAGNE "<token bot champagne da @BotFather>"
setx TELEGRAM_TOKEN_WHISKY    "<token bot whisky da @BotFather>"
setx TELEGRAM_CHAT_ID         "<il tuo chat id: scrivi /id al bot>"
echo Fatto. Chiudi e riapri le finestre dei bot.
pause
