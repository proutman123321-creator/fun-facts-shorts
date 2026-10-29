"""Build topic_plan.json: 730 topics (2 a day for one year), mixed across categories.

The first 60 (month 1) are fixed below; the rest are spread evenly so the same
category rarely comes twice in a row. Run: python src/build_plan.py
"""
import re
import sys
from datetime import date, timedelta

from common import ROOT, save_json

START = date(2026, 10, 30)
SLOTS = ["08:00", "20:00"]

CATEGORIES = {
    "Animals": (120, """octopuses, sharks, wombats, sloths, koalas, hummingbirds, butterflies, sea otters, elephants,
        giraffes, penguins, owls, crows, dolphins, whales, cats, dogs, horses, cows, pigs, chickens, ants, honeybees,
        spiders, snakes, crocodiles, frogs, axolotls, flamingos, kangaroos, platypuses, pandas, polar bears, camels,
        zebras, tigers, lions, cheetahs, wolves, foxes, rats, bats, hippos, rhinos, gorillas, chimpanzees, orangutans,
        parrots, peacocks, eagles, vultures, ostriches, tortoises, chameleons, geckos, jellyfish, starfish, seahorses,
        crabs, mantis shrimp, squids, snails, earthworms, mosquitoes, cockroaches, dragonflies, fireflies, ladybugs,
        termites, scorpions, tardigrades, hedgehogs, porcupines, squirrels, beavers, raccoons, skunks, armadillos,
        anteaters, capybaras, llamas, goats, sheep, reindeer, moose, bison, meerkats, hyenas, lemurs, red pandas,
        seals, walruses, manatees, narwhals, orcas, blue whales, pufferfish, clownfish, electric eels, piranhas,
        salmon, goldfish, honey badgers, Komodo dragons, pelicans, woodpeckers, swans, pigeons, rabbits, hamsters,
        mice, brown bears, okapis, pangolins, sea turtles, lobsters, cuttlefish, jaguars, leopards, moths"""),
    "History": (80, """ancient Egypt, the pyramids, Cleopatra, the Roman Empire, gladiators, Julius Caesar,
        ancient Greece, the Olympic Games, the Vikings, medieval knights, castles, samurai, ninjas, pirates,
        the Titanic, the Great Wall of China, Napoleon, the Aztecs, the Maya, the Incas, Machu Picchu, Stonehenge,
        the Colosseum, Pompeii, the Black Death, the Middle Ages, the Renaissance, Leonardo da Vinci, Shakespeare,
        Christopher Columbus, the Wild West, cowboys, the French Revolution, Marie Antoinette, Queen Elizabeth I,
        Henry VIII, Genghis Khan, Alexander the Great, the Spartans, mummies, Tutankhamun, hieroglyphs,
        the Silk Road, the Ottoman Empire, the Industrial Revolution, the Moon landing, the Space Race,
        Abraham Lincoln, George Washington, Roman baths, the Library of Alexandria, King Arthur, Robin Hood,
        the Trojan Horse, Mesopotamia, the Stone Age, cave paintings, Easter Island, Petra, the Terracotta Army,
        the Forbidden City, Hannibal, Charlemagne, Joan of Arc, Mozart, Beethoven, Isaac Newton, Galileo,
        Marco Polo, the Berlin Wall, the Gold Rush, ancient China, the Byzantine Empire, the Knights Templar,
        Harry Houdini, Queen Victoria, Catherine the Great, Benjamin Franklin, Roman roads, the pharaohs"""),
    "Space": (70, """the Sun, the Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto, black holes,
        neutron stars, galaxies, the Milky Way, comets, asteroids, meteorites, shooting stars,
        the International Space Station, astronauts, space suits, rockets, the Hubble telescope,
        the James Webb telescope, exoplanets, the Big Bang, dark matter, nebulas, supernovas, the Northern Lights,
        solar eclipses, the Andromeda galaxy, Saturn's rings, Jupiter's moons, Titan, Europa, Olympus Mons,
        the asteroid belt, space food, the Voyager probes, Mars rovers, the Apollo missions, Yuri Gagarin,
        Laika the space dog, space toilets, gravity, light-years, stars, red giants, white dwarfs, pulsars, quasars,
        wormholes, the Oort cloud, Halley's comet, Sirius, Betelgeuse, the North Star, constellations, sunspots,
        solar flares, the far side of the Moon, moonquakes, space junk, satellites, the speed of light,
        time in space, sunsets on Mars, cosmic rays, the Kuiper belt"""),
    "Human body": (70, """the brain, the heart, blood, bones, the skeleton, muscles, skin, hair, fingernails, teeth,
        the eyes, ears, the nose, the tongue, the stomach, the liver, the kidneys, the lungs, the intestines,
        gut bacteria, DNA, cells, the immune system, sleep, dreams, sneezing, hiccups, goosebumps, fingerprints,
        blinking, tears, sweat, blood types, babies, twins, left-handed people, the appendix, the spine, feet, hands,
        the human voice, the nervous system, reflexes, pain, the sense of smell, taste buds, height, aging, vitamins,
        water in the body, body temperature, hormones, adrenaline, red blood cells, white blood cells, the skull,
        saliva, the belly button, eyebrows, eyelashes, wisdom teeth, the funny bone, cracking knuckles,
        the heartbeat, brain freeze, color vision, the pancreas, the jaw, the knees, the thumb"""),
    "Science": (60, """water, ice, fire, electricity, magnets, lightning, rainbows, sound, light, colors, atoms, gold,
        diamonds, glass, plastic, iron, oxygen, carbon, helium, hydrogen, radioactivity, X-rays, lasers,
        absolute zero, boiling water, snowflakes, clouds, tornadoes, hurricanes, earthquakes, volcanoes, tsunamis,
        weather, the speed of sound, echoes, mirrors, soap bubbles, friction, rust, salt, sugar, batteries,
        glow-in-the-dark things, crystals, static electricity, viruses, bacteria, mold, fossils, dinosaurs, quicksand,
        the periodic table, sand, rain, fog, hail, thunder, wind, gravity on Earth, the atmosphere"""),
    "Places": (60, """Paris, the Eiffel Tower, New York, the Statue of Liberty, London, Big Ben, Tokyo, Venice, Rome,
        Dubai, the Burj Khalifa, the Grand Canyon, Niagara Falls, Mount Everest, the Sahara, the Amazon rainforest,
        Antarctica, the Arctic, Iceland, Greenland, Australia, Japan, Canada, Russia, China, India, Brazil, Mexico,
        Italy, Switzerland, Norway, the Netherlands, Vatican City, Monaco, Las Vegas, Hollywood, the Dead Sea,
        Yellowstone, the Alps, the Himalayas, the Nile, the Amazon River, Lake Baikal, the Maldives, Hawaii,
        Madagascar, the Galapagos Islands, Singapore, Istanbul, Barcelona, Angkor Wat, the Taj Mahal, Chernobyl,
        Death Valley, Uluru, Mount Fuji, Times Square, the London Underground, Scotland, Ireland"""),
    "Food": (50, """chocolate, coffee, tea, pizza, bread, cheese, honey, bananas, apples, strawberries, pineapples,
        avocados, tomatoes, potatoes, carrots, onions, garlic, chili peppers, rice, pasta, sushi, burgers,
        French fries, popcorn, ice cream, candy, chewing gum, peanuts, eggs, milk, butter, watermelons, lemons,
        oranges, coconuts, mushrooms, corn, olive oil, vanilla, cinnamon, ketchup, mustard, cereal, pancakes,
        croissants, hot dogs, donuts, soda, tacos, blueberries"""),
    "Ocean": (50, """the Mariana Trench, coral reefs, the Great Barrier Reef, tides, ocean waves, icebergs,
        the deep sea, anglerfish, giant squid, the Bermuda Triangle, ocean currents, the Gulf Stream,
        hydrothermal vents, bioluminescence, kelp forests, shipwrecks, submarines, scuba diving, beaches, sea foam,
        rogue waves, whirlpools, mangroves, the Pacific Ocean, the Atlantic Ocean, the Arctic Ocean,
        the Indian Ocean, the Southern Ocean, sea ice, ocean plastic, sea level, underwater volcanoes, sea caves,
        ocean pressure, the ocean floor, sea salt, lighthouses, sea urchins, sea cucumbers, sea sponges, barnacles,
        plankton, krill, oysters, pearls, blue holes, the Red Sea, the Sargasso Sea, marine snow, tide pools"""),
    "Inventions": (50, """the wheel, the printing press, the light bulb, the telephone, the internet, smartphones,
        computers, video games, television, radio, cameras, airplanes, cars, trains, bicycles, the steam engine,
        refrigerators, microwave ovens, sticky notes, Velcro, zippers, glasses, clocks, calendars, money, coins,
        paper, pencils, ballpoint pens, matches, toilets, umbrellas, elevators, escalators, robots,
        artificial intelligence, GPS, drones, 3D printing, vaccines, antibiotics, the stethoscope, the compass,
        the telescope, the microscope, solar panels, QR codes, barcodes, Wi-Fi, emojis"""),
    "Plants": (40, """trees, giant sequoias, bamboo, cactuses, sunflowers, roses, tulips, Venus flytraps,
        carnivorous plants, moss, ferns, algae, seaweed, grass, oak trees, baobab trees, redwoods, rainforests,
        leaves, flowers, pollen, seeds, the corpse flower, lotus flowers, orchids, poison ivy, fungi, lichens,
        bonsai trees, pine trees, palm trees, maple trees, cherry blossoms, dandelions, cotton, cocoa trees,
        olive trees, the oldest trees, desert plants, water lilies"""),
    "Records": (30, """the tallest buildings, the longest rivers, the biggest animals, the smallest animals,
        the fastest animals, the oldest animals, the hottest places on Earth, the coldest places on Earth,
        the deepest holes, the highest waterfalls, the longest bridges, the biggest countries,
        the smallest countries, the oldest people, the tallest people, the loudest animals,
        the most venomous animals, the longest flights, the fastest cars, the fastest trains, the biggest volcanoes,
        the largest deserts, the biggest waves, the most expensive things, the strongest animals,
        the biggest stadiums, the busiest airports, the longest tunnels, the deepest lakes, the biggest cities"""),
    "Words": (30, """the English language, the alphabet, slang, the word OK, palindromes, the longest words,
        sign language, the languages of the world, Latin, Chinese characters, Japanese writing, accents,
        tongue twisters, weird English spellings, English words from French, English words from Arabic,
        the letter X, the letter E, punctuation, words invented by Shakespeare, Morse code, secret codes,
        dead languages, Esperanto, animal sounds in other languages, the days of the week, the names of the months,
        idioms, hello around the world, baby talk"""),
    "Psychology": (20, """yawning, laughter, memory, deja vu, nightmares, fear, phobias, colors and mood,
        music and the brain, habits, procrastination, lying, smiling, boredom, happiness, the placebo effect,
        first impressions, multitasking, superstitions, nostalgia"""),
}

MONTH_1 = """octopuses, the Moon, chocolate, the brain, ancient Egypt, lightning, penguins, coral reefs,
    Mount Everest, the heart, cats, Mars, coffee, the Vikings, volcanoes, dolphins, the deep sea, the Eiffel Tower,
    sleep, honeybees, the Sun, bananas, the Roman Empire, airplanes, elephants, tornadoes, sharks, the Titanic,
    the eyes, Saturn, pizza, the Amazon rainforest, owls, icebergs, sunflowers, the fastest animals, dogs,
    black holes, the pyramids, bones, strawberries, snowflakes, butterflies, the Great Wall of China, Antarctica,
    smartphones, jellyfish, Jupiter, cheese, dreams, rainbows, kangaroos, Venice, the Mariana Trench, samurai,
    bamboo, the English language, giraffes, the Northern Lights, laughter"""


def split(text):
    return [t.strip() for t in text.replace("\n", " ").split(",") if t.strip()]


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def main():
    category_of, problems = {}, []
    for category, (target, text) in CATEGORIES.items():
        titles = split(text)
        if len(titles) != target:
            problems.append(f"{category}: {len(titles)} topics, expected {target}")
        for title in titles:
            if slug(title) in category_of:
                problems.append(f"duplicate: {title}")
            category_of[slug(title)] = (category, title)

    month_1 = [slug(t) for t in split(MONTH_1)]
    problems += [f"month 1 topic not in a category: {s}" for s in month_1 if s not in category_of]
    if problems:
        sys.exit("\n".join(problems))

    # spread the rest evenly: item k of a category with n items sits at position (k + 0.5) / n
    rest = []
    for category, (_, text) in CATEGORIES.items():
        items = [slug(t) for t in split(text) if slug(t) not in month_1]
        rest += [((k + 0.5) / len(items), category, s) for k, s in enumerate(items)]
    order = month_1 + [s for _, _, s in sorted(rest)]

    plan = []
    for i, s in enumerate(order):
        category, title = category_of[s]
        plan.append({"n": i + 1, "date": str(START + timedelta(days=i // 2)), "time": SLOTS[i % 2],
                     "id": s, "category": category, "title": title})
    save_json(ROOT / "topic_plan.json", plan)
    print(f"{len(plan)} topics, {plan[0]['date']} -> {plan[-1]['date']}")


if __name__ == "__main__":
    main()
