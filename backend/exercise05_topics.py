"""MVP 0.5 curated classification of previously unused CDB sources."""
SOURCE_TOPICS = {
    '10_traps.ru.cdb': 'дебютні пастки',
    '303_tactics.ru.cdb': 'тактичні комбінації',
    'ClaudeKabers.ru.cdb': 'тактичні комбінації',
    'Romanovsky.cdb': 'стратегія та план',
    'School2.ru.cdb': 'тактичні комбінації',
    'Shumilin.ru.cdb': 'тактичні комбінації',
    'Sukhin_1000.ru.cdb': 'історичні комбінації',
    'beginning.ru.cdb': 'тактичні комбінації',
    'bondarevsky.cdb': 'тактичні комбінації',
    'brilliant.cdb': 'навчальні партії',
    'koblents.cdb': 'тактичні комбінації',
    'kotov.cdb': 'стратегія та план',
    'lysenko.cdb': 'оцінка позиції',
    'suetin.cdb': 'дебютні принципи',
    'win_trap.ru.cdb': 'дебютні пастки',
}
NEW_TOPICS = tuple(dict.fromkeys(SOURCE_TOPICS.values()))
