# Kalkulator formatek

Desktopowa aplikacja dla Windows, z polskim interfejsem. **Wersja wyłącznie lokalna:** uruchomiony program nie wysyła szkiców ani innych danych do usług internetowych, nie wymaga kluczy API ani abonamentu. Trzy tryby: prostokąty, powielanie jednego nieregularnego obrysu oraz wspomagane odtworzenie konturu z wymiarów szkicu. Domyślny arkusz: 3050 × 2050 mm. Wszystkie wymiary w mm, akceptowany przecinek dziesiętny.

## Uruchomienie z Pythona

Wymagany Python 3.10–3.15 z Tkinter (Tcl/Tk w instalatorze Windows). W folderze projektu:

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements.txt
.venv-build\Scripts\python.exe app.py
```

Zależności: PyMuPDF (odczyt i zapis PDF), Shapely (geometria), NumPy (analiza pikseli skanów, bez OpenCV). Pobranie zależności podczas instalacji/budowania wymaga internetu. Gotowy EXE działa bez internetu; obliczenia, podgląd i import/eksport wykonują się wyłącznie na komputerze.

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

## Szkic → dowolny kontur

Zakładka tworzy dowolny prosty wielokąt z wymiarów. **Nie ma listy typów U/L/prostokąt.** Obsługiwane są odcinki poziome, pionowe i skośne oraz wklęsłości, maksymalnie 500 narożników. Nie jest to automatyczne rozpoznawanie odręcznego pisma ani automatyczna interpretacja rysunku. Łuki, krzywe i otwory nie są odtwarzane przez ten edytor; dla krzywych użyj istniejącego importu konturu wektorowego PDF.

1. Wczytaj PDF (pierwsza strona) lub obraz. Obróć podgląd przed zaznaczaniem narożników. **Podgląd 100% / dopasuj** i paski przewijania pozwalają obejrzeć szczegóły.
2. Klikaj kolejne narożniki po obwodzie formatki, bez linii wymiarowych, podpisów i powtarzania pierwszego punktu. Każdy punkt otrzymuje numer P1, P2 itd. Kliknij **Zamknij kontur**. Czerwony obrys na szkicu pokazuje wyłącznie kolejność punktów.
3. W tabeli boków wpisz **ΔX i ΔY w mm**: przesunięcie od punktu początkowego do końcowego. W prawo X dodatnie, w lewo ujemne; w dół Y dodatnie, w górę ujemne. Wartość 0 oznacza brak zmiany w danej osi. Puste oznacza brakujący wymiar, który trzeba wyliczyć z innych wpisanych danych lub uzupełnić. Ostatni bok wraca do P1.
4. Opcja **Podpowiadaj poziom/pion** wpisuje 0 w jednej osi, jeśli kliknięty bok jest wyraźnie poziomy lub pionowy. Jest to edytowalna propozycja kierunku, nigdy pomiar długości. Wyłącz ją dla dowolnych skosów lub popraw 0 ręcznie. Żadna długość ani kąt nie są mierzone z proporcji obrazka.
5. Jeśli szkic podaje szerokość całkowitą lub wysokość zamiast długości poszczególnych boków, użyj **Dodaj wymiar między punktami**. Wskaż dwa dowolne ponumerowane punkty, oś X lub Y oraz podpisaną różnicę w mm. Wartość 0 pozwala wskazać, że odległe narożniki leżą na tym samym poziomie lub pionie. Dla skosu trzeba podać rzuty ΔX/ΔY lub inne wymiary jednoznacznie je określające; samej długości skośnej nie należy wpisywać jako ΔX.
6. Kliknij **Zbuduj i sprawdź kontur**. Program rozwiązuje relacje wymiarowe i wylicza brakujące współrzędne, bez pomiaru skanu. Jeśli brakuje danych, wymienia punkty i osie do uzupełnienia. Sprzeczne wymiary, brak zamknięcia, powtarzające się punkty, samoprzecięcia i zerowe pole są odrzucane. Zgodność nadmiarowych wymiarów sprawdzana jest z tolerancją 0,001 mm.
7. Porównaj wygenerowany kontur i numerację ze szkicem. Wymiary całkowite i pole są obliczane z podanych danych. Zaznacz **Potwierdzam kontur i wymiary**, a następnie przekaż go do układania albo zapisz jako PDF 1:1. Każda zmiana wymiarów unieważnia zatwierdzenie. PDF nie zawiera numerów punktów ani linii wymiarowych.

Wczytanie innego szkicu czyści narożniki i wymiary. Przy obrocie szkicu lub otwarciu zamkniętego konturu do edycji program pyta o usunięcie przypisanych wymiarów.

### Przykład BV300 bez szablonu figury

Zaznacz narożniki w tej kolejności: lewy górny P1, prawy górny P2, prawy dolny P3, wewnętrzny prawy dolny P4, wewnętrzny prawy górny P5, wewnętrzny lewy górny P6, wewnętrzny lewy dolny P7, lewy dolny P8. Po podpowiedzi H/V wpisz:

| Bok | ΔX [mm] | ΔY [mm] |
| --- | ---: | ---: |
| P1 → P2 | 440 | 0 |
| P2 → P3 | 0 | 160 |
| P3 → P4 | -60 | 0 |
| P4 → P5 | 0 | pozostaw puste |
| P5 → P6 | pozostaw puste | 0 |
| P6 → P7 | 0 | pozostaw puste |
| P7 → P8 | -30 | 0 |
| P8 → P1 | 0 | pozostaw puste |

Dodaj dwa wymiary: P1 → P5 w osi Y = 30 mm (poprzeczka) oraz P3 → P7 w osi Y = 0 mm (wspólny dolny poziom). Program obliczy pozostałe wartości: zewnętrzne 440 × 160 mm, wycięcie 350 × 130 mm, pole 24 900 mm². Ten sam mechanizm działa dla dowolnej liczby i układu narożników.

## Weryfikacja

```bat
.venv-build\Scripts\python.exe -m unittest -v
```

Testy obejmują prostokąty, nieregularne wcięcia, układanie trójkątów gęściej niż ich prostokąty otaczające, odstępy i marginesy, obrót, anulowanie, import PDF z krzywymi, skan i skalę eksportu PDF 1:1.

PyMuPDF jest dostępny na licencji AGPL lub komercyjnej. Przed dystrybucją aplikacji uwzględnij warunki licencji jej zależności.
