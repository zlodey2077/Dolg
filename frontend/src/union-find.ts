/**
 * Union-find (disjoint-set) для электрических узлов схемы.
 *
 * Используется в SPICE-генераторе и в Ω-режиме мультиметра лаборатории —
 * объединяет порты компонентов в эквипотенциальные узлы по соединениям.
 *
 * Это TS-версия логики из shop/static/simulation/scheme-netlist.js
 * (createUnionFind / portKey / connectPorts). Поддерживает path-compression
 * через iterative two-step grandparent shortcut. По бенчмаркам — на 600
 * портах работает за < 1 мс.
 */

export type PortKey = string;

export interface UnionFind {
    find(key: PortKey): PortKey;
    union(left: PortKey, right: PortKey): void;
    /** Sneak peek: для тестов и отладки. */
    readonly parent: ReadonlyMap<PortKey, PortKey>;
}

export function portKey(componentId: number | string, portId: number | string): PortKey {
    return `${componentId}:${portId}`;
}

export function createUnionFind(): UnionFind {
    const parent = new Map<PortKey, PortKey>();

    function find(key: PortKey): PortKey {
        if (!parent.has(key)) parent.set(key, key);
        // Path-compression two-step (grandparent shortcut). Обычно достаточно
        // и быстрее full path-compression — нет рекурсии и аллокаций.
        let cur = key;
        while (parent.get(cur) !== cur) {
            const grandparent = parent.get(parent.get(cur)!)!;
            parent.set(cur, grandparent);
            cur = grandparent;
        }
        return cur;
    }

    function union(left: PortKey, right: PortKey): void {
        const leftRoot = find(left);
        const rightRoot = find(right);
        if (leftRoot !== rightRoot) parent.set(leftRoot, rightRoot);
    }

    return {
        find,
        union,
        parent,
    };
}
