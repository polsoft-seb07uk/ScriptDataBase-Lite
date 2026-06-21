# 🗄️ ScriptDataBase Lite

Lekka aplikacja desktopowa do przechowywania, organizowania i uruchamiania skryptów — Python, Bash, PowerShell, Batch, JavaScript, SQL, VBScript, Ruby, Lua i inne — z jednej przeszukiwalnej biblioteki.

![ScriptDataBase Lite screenshot](screenshot.png)

![Version](https://img.shields.io/badge/version-3.0.8-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Qt](https://img.shields.io/badge/UI-PyQt6-green)
![License](https://img.shields.io/badge/license-Freeware-lightgrey)

## Przegląd

ScriptDataBase Lite to aplikacja desktopowa napisana w PyQt6 dla programistów i zaawansowanych użytkowników, którzy gromadzą dużo małych skryptów narzędziowych i potrzebują szybkiego sposobu ich odnajdywania, edycji i ponownego uruchamiania. Zamiast przeszukiwać rozproszone foldery, skrypty przechowywane są w jednej przeszukiwalnej bibliotece z kolorowaniem składni, tagami, kategoriami, statystykami uruchomień i możliwością uruchomienia jednym kliknięciem w wybranym terminalu. Aplikacja jest zorganizowana w pięć zakładek — **New/Edit**, **My Scripts**, **Settings**, **Snippets** i **Statistics** — dostępnych z paska zakładek, menu lub przez skróty klawiaturowe.

## Funkcje

### ➕ New / Edit — edytor skryptów

- Pola formularza dla **nazwy**, **kategorii** (jedna z obsługiwanych), oddzielonych przecinkami **tagów** i krótkiego **opisu**.
- Pełnowartościowy edytor kodu (oparty na `QPlainTextEdit`) z **numerami linii**, stałej szerokości fontem monospace oraz **Ctrl+H** do szybkiego uruchomienia znajdź/zamień z poziomu edytora.
- **Automatyczne wykrywanie języka**: skanuje wklejony kod według zestawu wzorców regex (shebangi, słowa kluczowe, idiomy składniowe) i ustawia kategorię oraz podświetlanie składni automatycznie. To samo wykrywanie działa po otwarciu pliku przez **Ctrl+O**.
- **Kolorowanie składni** zmienia się natychmiast po zmianie kategorii.
- **Znajdź / Zamień** (`Ctrl+H`): wyszukiwanie uwzględniające wielkość liter, całe słowa i tryb wyrażeń regularnych; zamień pojedyncze dopasowanie lub **zamień wszystko** w jednym bloku, możliwym do cofnięcia, z licznikiem dokonanych zamian.
- **Podgląd różnic**: podczas edycji istniejącego skryptu "📊 Podgląd zmian" otwiera widok unified-diff porównujący ostatnio zapisane wersje z bieżącymi zmianami, z kolorowaniem dodanych/usuniętych linii i podsumowaniem. (Wyłączone dla nowych, jeszcze niezapisanych skryptów.)
- **Śledzenie niezapisanych zmian**: pasek stanu pokazuje liczbę linii/znaków na żywo, a aplikacja nie odrzuca edycji bez potwierdzenia (przy czyszczeniu edytora, przełączaniu zakładek lub zamykaniu aplikacji).
- **Ochrona przed duplikatami nazw**: zapisanie nowego skryptu o nazwie już istniejącej w bibliotece wymaga potwierdzenia przed utworzeniem drugiego wpisu.
- **Eksport z edytora**: zapisz zawartość edytora bezpośrednio do pliku (z odpowiednim rozszerzeniem dla wybranej kategorii), niezależnie od zapisu do biblioteki.
- **Kopiuj kod** do schowka lub **Wyczyść** edytor (z potwierdzeniem jeżeli są niezapisane zmiany).

### 📋 My Scripts — biblioteka, wyszukiwanie i uruchamianie

- Widok dzielony: lista filtrów po lewej, podgląd z kolorowanym kodem po prawej.
- **Wyszukaj** w nazwie, tagach i opisie z debounce 150 ms, aby wpisywanie pozostawało płynne; opcjonalne **"Szukaj w kodzie"** rozszerza wyszukiwanie na treść skryptu i podświetla dopasowania.
- Rozwijany filtr **Kategoria** i przełącznik **Tylko ulubione** dla zawężania listy.
- **Przypięte/ulubione skrypty** (`📌`) zawsze znajdują się na górze listy, niezależnie od sortowania i filtrów.
- Panel podglądu pokazuje kategorię, tagi, datę, opis i statystyki uruchomień (liczba uruchomień + ostatnie uruchomienie) obok tylko do odczytu, kolorowanego kodu.
- Działania na skrypcie dostępne jako przyciski, menu kontekstowe lub podwójne kliknięcie: **Edytuj**, **Uruchom**, **Przypnij/Odprzypnij**, **Kopiuj kod**, **Duplikuj** (tworzy niezależną kopię z własnymi statystykami), **Eksportuj do pliku** i **Usuń** (z opcjonalnym potwierdzeniem, konfigurowalnym w Ustawieniach).
- Liczba skryptów jest zawsze widoczna na dole listy.

### ▶ Uruchamianie skryptów

- Otwórz dialog Uruchom dla wybranego skryptu lub uruchom skrypt otwarty w edytorze przez **Ctrl+Enter** bez konieczności zapisu.
- Skrypt zapisywany jest do pliku tymczasowego z odpowiednim rozszerzeniem i wykonany; można podać opcjonalne argumenty wiersza poleceń.
- **Skrypty Python** wykonywane są w wątku roboczym, aby UI pozostał responsywny; wyjście jest **strumieniowane linia po linii** (zamiast czekać na zakończenie procesu), aplikacja ma wbudowany **30-sekundowy timeout** na zatrzymanie niekończących się procesów oraz przycisk **Stop** do ręcznego zakończenia.
- **Inne języki** (Bash, PowerShell, Batch itp.) uruchamiane są w automatycznie wykrytym terminalu systemowym — aplikacja sprawdza dostępność CMD, PowerShell, PowerShell Core, Bash, sh, Zsh i WSL przy starcie (**Tools → 🔄 Detect terminals** aby ponownie przeskanować) i pozwala wybrać, którego użyć.
- Opcja automatycznego usuwania pliku tymczasowego po zakończeniu wykonania (domyślnie włączona).
- Każde udane uruchomienie aktualizuje licznik uruchomień i znacznik czasu ostatniego uruchomienia, co zasila zakładkę Statystyki.

### 🧩 Snippets — fragmenty kodu do ponownego użycia

- Niezależna mini-biblioteka (osobny plik `snippets.json`) dla krótkich, wielokrotnego użytku fragmentów kodu — boilerplate, one-linery, idiomy — oddzielona od pełnych skryptów.
- Własne pole wyszukiwania i filtr kategorii oraz dedykowany edytor z podświetlaniem składni do tworzenia i edycji snippetów.
- **"⏎ Wstaw do edytora"** wkleja kod snippet-a do głównego edytora na aktualnej pozycji kursora i przełącza na kartę New/Edit; podwójne kliknięcie również to wykonuje.
- **"🧩 Zapisz zaznaczenie jako snippet"** (menu Edycja) wysyła zaznaczony tekst — lub cały skrypt jeśli nic nie jest zaznaczone — do nowego snippetu.
- Akcje Nowy, Zapisz, Wstaw, Kopiuj i Usuń oraz menu kontekstowe prawego przycisku.
- Motyw i fonty edytora są współdzielone z resztą aplikacji.

### 📊 Statystyki

- Dostępne jako stała zakładka oraz jako szybkie okno modalne (**Tools → Statistics**, `Ctrl+T`).
- Linia podsumowania z liczbą skryptów, liczbą przypiętych ulubionych i sumą uruchomień w bibliotece.
- **Skrypty według kategorii** — tabela z podziałem według liczby.
- **Najczęściej uruchamiane** — top 10 według liczby uruchomień.
- **Przypięte skrypty** — szybka lista wszystkich zaznaczonych jako ulubione.
- Przyciski **Odśwież** przebudowują listy z aktualnych danych.

### ⚙️ Ustawienia

- **Motyw**: przełącznik między ciemnym i jasnym motywem; zmiana stosowana natychmiast we wszystkich edytorach i podglądach.
- **Język**: przełącz interfejs pomiędzy polskim i angielskim (aplikacja restartuje się, aby zastosować zmianę, z wcześniejszym potwierdzeniem).
- **Czcionka edytora**: wybierz rodzinę (Consolas, Courier New, Fira Code, JetBrains Mono, Cascadia Code, Monospace) i rozmiar (7–24pt); stosowane od razu w New/Edit, My Scripts i Snippets.
- **Potwierdź przed usunięciem**: przełącznik, czy usuwanie ma pytać o potwierdzenie.
- **Kolejność zakładek**: zmieniaj kolejność pięciu głównych zakładek przez przeciąganie elementów w liście w Ustawieniach lub przez przeciąganie samych zakładek — obie metody są synchronizowane i zapamiętywane między sesjami.
- **Przywróć domyślne** przywraca domyślny motyw, font i kolejność zakładek.
- Ustawienia zapisywane są przyciskiem **Zapisz ustawienia** (lub automatycznie przy zmianie motywu/języka) i trwale przechowywane w `settings.json`.

### 📥📤 Import / Eksport

- **Import skryptów (JSON)**: wczytaj tablicę JSON skryptów z walidacją rekordów — brak `name`/`code` jest raportowany, nieznane kategorie są mapowane na "Other", otrzymujesz podsumowanie ile rekordów nie przeszło walidacji przed decyzją o imporcie poprawnych.
- **Eksport wszystkie (JSON)**: zrzut całej biblioteki do jednego pliku JSON.
- **Eksport wszystkie (ZIP)**: zapisuje każdy skrypt jako osobny plik, posegregowany do podfolderów per-kategoria (np. `Python/backup_documents.py`), z automatycznym obsługiwaniem duplikatów nazw plików i dodatkowym `_metadata/scripts.json` zawierającym pełne rekordy.
- **Eksport z edytora** i **eksport pojedynczego skryptu** pozwalają zapisać skrypt na dysku w dowolnym momencie.
- **Otwórz folder danych** otwiera katalog, w którym przechowywane są pliki JSON.

### 🌐 Interfejs i personalizacja

- Pełne **ciemne i jasne motywy**.
- **Tłumaczenia: polski i angielski**, możliwe do przełączenia z menu Język lub Ustawień.
- **Przeciągane zakładki** — możliwość przeciągania zakładek bezpośrednio na pasku oraz z poziomu listy w Ustawieniach.
- Rozmiar i pozycja okna zapamiętywane są między sesjami i przywracane na środku ekranu.

### 🛡️ Integralność danych i magazyn

- Wszystkie dane to lokalne pliki JSON, zapisywane atomowo (najpierw do tymczasowego pliku, potem rename), aby przerwanie zapisu nie mogło uszkodzić biblioteki.
- Jeżeli plik danych zostanie wykryty jako uszkodzony przy starcie, zostaje zapisany jako kopia zapasowa z sygnaturą czasową zamiast być bez śladu usunięty, a problem jest logowany.
- Automatyczna **migracja wsteczna**: starsze `scripts.json` bez pól pinned/run-count/last-run są poprawiane przy starcie.
- ID skryptów to UUID4, co eliminuje kolizje przy szybkim tworzeniu wielu rekordów.

| Plik | Zawartość |
|---|---|
| `scripts.json` | Twoja biblioteka skryptów |
| `snippets.json` | Zapisane fragmenty kodu |
| `settings.json` | Motyw, język, czcionka, kolejność zakładek i inne preferencje |

### ℹ️ Okno "O programie"

Pokazuje wersję aplikacji, autora i dane kontaktowe, licencję oraz informacje o środowisku (wersja Pythona, platforma OS i aktywny katalog danych) — dostępne z **Help → About**.

## Wymagania

- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/)

```bash
pip install PyQt6
```

## Uruchamianie

```bash
python ScriptDataBase.py
```

Przy pierwszym uruchomieniu aplikacja tworzy katalog danych i zaczyna z pustą biblioteką — dodaj pierwszy skrypt z zakładki **New / Edit**.

## Skróty klawiaturowe

| Skrót | Akcja |
|---|---|
| `Ctrl+N` | Nowy skrypt |
| `Ctrl+O` | Otwórz plik w edytorze |
| `Ctrl+S` | Zapisz skrypt |
| `Ctrl+Enter` | Uruchom aktualny skrypt z edytora |
| `Ctrl+E` | Edytuj wybrany skrypt |
| `Ctrl+R` | Uruchom wybrany skrypt |
| `Ctrl+Shift+C` | Kopiuj kod wybranego skryptu |
| `Ctrl+P` | Przypnij / od przypnij skrypt |
| `Delete` | Usuń wybrany skrypt |
| `Ctrl+H` | Znajdź / Zamień w edytorze |
| `Ctrl+T` | Otwórz Statystyki |
| `Alt+F4` | Zakończ |

## Obsługiwane kategorie skryptów

| Kategoria | Rozszerzenie |
|---|---|
| Python | `.py` |
| Bash | `.sh` |
| PowerShell | `.ps1` |
| Batch | `.bat` |
| JavaScript | `.js` |
| SQL | `.sql` |
| VBScript | `.vbs` |
| Ruby | `.rb` |
| Lua | `.lua` |
| Other | `.txt` |

## Licencja

Freeware. Do użytku i rozpowszechniania w niezmienionej formie, z zachowaniem przypisania autorstwa.

## Autor

**Sebastian Januchowski** — polsoft.ITS™ Group
[GitHub](https://github.com/polsoft-seb07uk) · [polsoft.its@fastservice.com](mailto:polsoft.its@fastservice.com)
