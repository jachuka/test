# Kalkulator formatek

Desktopowa aplikacja dla Windows, z polskim interfejsem. Trzy tryby: prostokąty, powielanie jednego nieregularnego obrysu oraz wspomagane odtworzenie konturu z wymiarów szkicu. Domyślny arkusz: 3050 × 2050 mm. Wszystkie wymiary w mm, akceptowany przecinek dziesiętny.

## Uruchomienie z Pythona

Wymagany Python 3.10–3.15 z Tkinter (Tcl/Tk w instalatorze Windows). W folderze projektu:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements.txt
.venv-build\Scripts\python.exe app.py
```

Zależności: PyMuPDF (odczyt i zapis PDF), Shapely (geometria), NumPy (analiza pikseli skanów, bez OpenCV). Instalacja wymaga internetu; obliczenia i import/eksport działają lokalnie.

## Plik EXE dla Windows 11

Pobierz Code → Download ZIP z GitHub, rozpakuj do nowego folderu i uruchom `Zbuduj_EXE.bat`. Skrypt instaluje zależności w `.venv-build`, sprawdza Tkinter, uruchamia testy i buduje `dist\KalkulatorFormatek.exe`.

Jeśli Windows blokuje skrypt BAT, otwórz folder w Eksploratorze, wpisz `cmd` w pasku adresu i wykonaj kolejno:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install PyInstaller==6.22.3 -r requirements.txt
.venv-build\Scripts\python.exe -m unittest -v
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name KalkulatorFormatek app.py
```

Po wyniku testów `OK` można uruchomić ostatnie polecenie. Gotowy EXE nie wymaga Pythona. Przy aktualizacji należy ponownie zbudować EXE. Plik nie jest podpisany cyfrowo; Windows może ograniczyć jego uruchomienie. Budowanie EXE wymaga Windows i nie zostało zweryfikowane w linuksowym środowisku chmurowym.

## Prostokąty

Wprowadź wymiary arkusza i jednej formatki, odstęp między krawędziami i margines od wszystkich brzegów. Obrót o 90° można wyłączyć, np. ze względu na kierunek materiału. Kalkulator porównuje poziome i pionowe układy pasowe, również z mieszanymi orientacjami; nie gwarantuje optimum dowolnego pakowania. Limit podglądu: 50 000 formatek.

## Kształty nieregularne / PDF

1. Wybierz zakładkę **Kształty nieregularne / PDF**.
2. Wczytaj **PDF wektorowy 1:1**. Odczytywana jest wyłącznie pierwsza strona i zamknięte, poprawne geometrycznie obrysy mieszczące się w całości na widocznej stronie. Obiekty poza stroną i obrysy przycięte jej brzegiem są pomijane. Z CorelDRAW wyeksportuj sam kontur jako krzywą w PDF 1:1; bez napisów i znaczników. CDR nie jest obsługiwany.
3. Jeśli plik zawiera kilka obrysów, wybierz właściwy z listy. Podgląd i rozmiar pozwalają odróżnić formatkę od ramki strony. Jeden wybrany obrys jest jedną formatką; pozostałe nie są łączone w grupę.
4. Alternatywnie wczytaj skan PDF lub PNG/JPG/BMP: ciemny, zamknięty obrys lub sylwetka na białym tle. Ustaw próg ciemności (domyślnie 180), wybierz kontur i podaj jego **rzeczywistą szerokość w mm**. Skala DPI skanu nie jest uznawana za wiarygodną. Program zachowuje proporcje obrazu; nie koryguje perspektywy ani zniekształceń skanera. Koniecznie sprawdź obrys i wysokość w podglądzie. Gdy kalibracja zostanie anulowana, wybierz obrys ponownie.
5. Ustaw arkusz, odstęp i margines. Włączenie obrotów dopuszcza 0°, 90°, 180°, 270°; odbicie lustrzane nie jest stosowane.
6. Kliknij **Ułóż formatki**. Najpierw powstaje pełny układ regularny. Następnie program sprawdza powtarzalne grupy dopasowanych obrysów i zachowuje wynik z większą liczbą formatek. Czas optymalizacji można wybrać: 15, 30, 60 lub 120 sekund (domyślnie 30). Obliczenia działają w tle, do 1000 kopii; można je przerwać i zachować najlepszy dotychczasowy układ. Limit czasu nie usuwa pełnego układu bazowego. Poszukiwanie nie gwarantuje optimum ani wykorzystania każdego wolnego miejsca.
7. Kliknij **Zapisz układ do PDF 1:1**. PDF ma rozmiar arkusza i czarne obrysy wektorowe; nie zawiera ramki arkusza, wymiarów ani podpisów jako linii cięcia. Eksport zapisuje widoczny wynik z wymiarami podanymi w opisie wyniku, również jeśli później zmienisz pola formularza bez ponownego obliczenia. Maksymalny bok eksportowanego arkusza: 5080 mm. Przy druku wybierz rzeczywisty rozmiar / 100%, bez dopasowania do strony.

Układanie używa geometrii obrysów i sprawdza kolizje oraz odstęp, zamiast traktować każdy obrys jako prostokąt. Jest heurystyczne: nie gwarantuje największej możliwej liczby. Krzywe są przybliżane odcinkami z tolerancją 0,05 mm; dla odstępu stosowany jest dodatkowy zapas 0,1 mm. Otwory są traktowane jako pełny materiał; nie są eksportowane jako wycięcia. Skan jest aproksymacją obrysu, nie dokładnym plikiem produkcyjnym. Przed cięciem zweryfikuj wymiary i geometrię w swoim programie produkcyjnym. W odstępie uwzględnij szerokość cięcia.

Obsługa wielu różnych formatek z zadanymi ilościami, otworów i dowolnych kątów obrotu nie jest częścią tej wersji.

## Szkic → kontur

Nowa zakładka odtwarza dokładną geometrię **z wpisanych wymiarów**, bez mierzenia proporcji obrazka. Obsługiwane typy: U, L i prostokąt. Możesz wpisać dane ręcznie albo użyć odczytu przez OpenAI API. Odczyt AI rozpoznaje propozycję typu i zapisanych wymiarów; nie zatwierdza geometrii. Pozostałe kształty nadal wymagają przygotowanego konturu PDF. Ręczne wpisywanie działa offline; AI wymaga internetu i własnego dostępu do API. Nie dodaje nowych bibliotek ani OpenCV.

1. Wczytaj szkic PDF (pierwsza strona) lub obraz PNG/JPG/BMP. Pokazuje się jako odniesienie; podgląd można obracać o 90°. Skala skanu nie jest używana do obliczeń. Wczytanie innego pliku czyści poprzednie wymiary i zatwierdzenie.
2. Wybierz typ figury i przypisz wymiary ze szkicu do opisanych pól. Szerokość i wysokość są zawsze **zewnętrzne**. Dla U poprzeczka znajduje się u góry, a ramiona są skierowane w dół. Dla L poprzeczka jest u góry, a ramię po lewej; orientację konturu podczas układania można zmieniać dotychczasowym przełącznikiem obrotów.
3. Pola są początkowo puste. Nieczytelne wymiary trzeba wyjaśnić z klientem i wpisać. Wymiary wycięcia mogą pozostać puste, jeśli da się je wyliczyć z innych podanych wymiarów. Program stosuje wyłącznie relacje wymiarowe: dla U szerokość wycięcia = szerokość zewnętrzna − lewe ramię − prawe ramię; głębokość wycięcia = wysokość zewnętrzna − poprzeczka. Można też podać wymiary wycięcia i wyliczyć brakujący wymiar zewnętrzny. Program nie przyjmuje żadnej wartości na podstawie wyglądu szkicu.
4. Kliknij **Zbuduj i sprawdź kontur**. Brak danych albo sprzeczność zatrzymuje budowanie. Nadmiarowe wymiary muszą zgadzać się w granicach 0,001 mm.
5. Porównaj kontur i etykiety wymiarów ze szkicem. Zaznacz **Potwierdzam kształt i wymiary**. Każda zmiana danych unieważnia kontur i zatwierdzenie.
6. Kliknij **Zatwierdź i przejdź do układania**, żeby użyć konturu w trybie nieregularnym. Alternatywnie zapisz sam kontur jako PDF 1:1, bez opisów i linii wymiarowych.

Przykład BV300: U, szerokość zewnętrzna 440, wysokość zewnętrzna 160, poprzeczka 30, lewe ramię 30, prawe ramię 60 mm. Wynik: wycięcie 350 × 130 mm, pole materiału 24 900 mm². Podanie przy tym głębokości wycięcia 160 mm jest sprzeczne i zostaje odrzucone. Ten kontur porównano z poprawnym PDF użytkownika: odchylenie poniżej 0,001 mm.

Tryb pozwala zbudować i zweryfikować kontur bez ręcznego rysowania w programie graficznym.

### Odczyt szkicu przez AI

1. Utwórz klucz na https://platform.openai.com/api-keys i zapewnij środki/dostęp do modelu na koncie API. Rozliczenie API jest niezależne od abonamentu ChatGPT.
2. W aplikacji wybierz **Szkic → kontur → Ustawienia AI / klucz dostępu**. Wpisz klucz lokalnie; nie wysyłaj go w rozmowie ani w plikach projektu. Klucz pozostaje w pamięci do zamknięcia aplikacji. Alternatywnie aplikacja odczytuje lokalne `FORMATKI_OPENAI_API_KEY` lub `OPENAI_API_KEY`. Kluczy nie należy wpisywać do skryptu BAT, README ani kodu.
3. Domyślny model to `gpt-4.1`. Możesz wpisać inny dostępny na Twoim koncie model obsługujący obrazy i Structured Outputs w Responses API. Brak dostępu lub nieobsługiwany model jest zgłaszany jako błąd, bez zastępowania danych zgadywanymi wartościami.
4. Wczytaj szkic i ewentualnie obróć podgląd. Kliknij **Odczytaj szkic przez OpenAI**. Dopiero ten przycisk wysyła do `https://api.openai.com/v1/responses` obraz pierwszej strony, w orientacji podglądu, wraz z poleceniem odczytu i schematem danych. Pełny oryginalny PDF nie jest przesyłany. Zapytanie jest płatne według cennika użytego modelu. Zapytanie ustawia `store: false`; nie stanowi to gwarancji braku przetwarzania lub retencji po stronie dostawcy — obowiązują warunki OpenAI API.
5. Poczekaj na raport i propozycję. AI ma odczytywać tylko jawne wymiary z napisów i strzałek, bez pomiaru pikseli, skali kratki, domniemanej symetrii ani obliczania brakujących liczb. Do pól trafiają wyłącznie dodatnie, skończone liczby w mm oznaczone przez model jako jednoznaczne i zawierające opis odczytu. Nieznany typ lub jednostki blokują przeniesienie wymiarów. Niepewne wymiary pozostają puste; raport pokazuje pytania i uwagi.
6. Jeśli danych wystarcza, aplikacja tworzy propozycję konturu, sprawdzając relacje wymiarowe tak samo jak przy wpisywaniu ręcznym. Obejrzyj raport, porównaj KAŻDY wymiar ze szkicem i wyjaśnij niejasności z klientem. AI może błędnie rozpoznać lub przypisać liczbę nawet wtedy, gdy oznaczy ją jako pewną. Kontur nadal wymaga zaznaczenia potwierdzenia przed przekazaniem do układania lub eksportem.

Odczyt działa w tle; limit połączenia wynosi 90 sekund. Zmiana szkicu, jego obrotu, rodzaju lub wymiarów podczas odczytu powoduje odrzucenie nieaktualnego wyniku. Błędy klucza, sieci i limitów nie zmieniają wpisanych wymiarów. Nie ma automatycznego ponawiania płatnych zapytań. Żądania nie podążają za przekierowaniami HTTP, a TLS jest weryfikowany standardowo. Aplikacja nie zapisuje klucza na dysku ani nie wyświetla surowych błędów serwera.

Integrację sprawdzono na symulowanych odpowiedziach API (format żądania, błędy, niejednoznaczne wymiary, walidacja). Brak klucza w środowisku chmurowym uniemożliwił test na rzeczywistym modelu i ocenę trafności odczytu odręcznego BV300. Po lokalnym skonfigurowaniu dostępu pierwszy odczyt wymaga sprawdzenia na znanym przykładzie: U, 440 × 160 mm, poprzeczka 30 mm, ramiona 30 i 60 mm, wycięcie 350 × 130 mm.

## Weryfikacja

```bat
.venv-build\Scripts\python.exe -m unittest -v
```

Testy obejmują prostokąty, nieregularne wcięcia, układanie trójkątów gęściej niż ich prostokąty otaczające, odstępy i marginesy, obrót, anulowanie, import PDF z krzywymi, skan i skalę eksportu PDF 1:1.

PyMuPDF jest dostępny na licencji AGPL lub komercyjnej. Przed dystrybucją aplikacji uwzględnij warunki licencji jej zależności.
