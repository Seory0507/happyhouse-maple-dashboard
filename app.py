                f'⚔️ {html.escape(display_name)}',
                '</div>',
                '<div class="completed-boss-info">',
                f'{used_parties}개 파티 · 총 편성 {member_count}명',
                '</div>',
                '</div>',
            ])

            st.markdown(completed_html, unsafe_allow_html=True)

            c1, c2 = st.columns(2)

            with c1:
                if st.button(
                    "✏️ 불러오기 / 수정",
                    key=f"load_boss_{index}",
                    use_container_width=True,
                ):
                    st.session_state["pending_load_boss"] = display_name
                    st.rerun()

            with c2:
                if st.button(
                    "🗑️ 삭제",
                    key=f"delete_boss_{index}",
                    use_container_width=True,
                ):
                    del st.session_state.completed_bosses[display_name]
                    st.session_state["show_final_result"] = False
                    st.rerun()

        st.divider()

        if st.button(
            "🏁 전체 파티 구성 완료",
            type="primary",
            use_container_width=True,
            key="finish_all_parties",
        ):
            st.session_state["show_final_result"] = True
            st.rerun()

    if st.session_state.show_final_result and st.session_state.completed_bosses:
        st.divider()

        st.markdown(
            """
<div class="party-page-title">
🏆 해피하우스 보스 파티 편성표
</div>
""",
            unsafe_allow_html=True,
        )

        for display_name, boss_data in st.session_state.completed_bosses.items():
            final_parts = [
                '<div class="final-boss-card">',
                '<div class="final-boss-name">',
                f'⚔️ {html.escape(display_name)}',
                '</div>',
            ]

            for members in boss_data["parties"]:
                if not members:
                    continue

                names = [
                    html.escape(character_lookup[cid]["nickname"])
                    for cid in members
                ]

                total_combat, avg_hexa = calculate_party_stats(members)

                final_parts.extend([
                    '<div class="final-party-line">',
                    " / ".join(names),
                    '<div class="final-party-stat">',
                    f'총 전투력 {format_combat_power(total_combat)}',
                    '&nbsp;&nbsp;·&nbsp;&nbsp;',
                    f'평균 헥사 {format_hexa(avg_hexa)}',
                    '</div>',
                    '</div>',
                ])

            final_parts.append('</div>')

            st.markdown("".join(final_parts), unsafe_allow_html=True)

        final_text = build_final_text()

        with st.expander("📋 텍스트 결과 보기"):
            st.code(final_text, language=None)

        png_bytes = make_party_image()

        if png_bytes:
            st.image(
                png_bytes,
                caption="최종 파티 편성 이미지",
                use_container_width=True,
            )

            st.download_button(
                "🖼️ 파티 편성표 이미지 저장",
                data=png_bytes,
                file_name="해피하우스_보스파티_편성표.png",
                mime="image/png",
                use_container_width=True,
            )
